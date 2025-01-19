import os
from typing import List, Dict, Any, Optional
from supabase import create_client, Client
import numpy as np
from openai import OpenAI
import tiktoken

class SupabaseVectorStore:
    def __init__(self):
        url: str = os.environ.get("SUPABASE_URL")
        key: str = os.environ.get("SUPABASE_KEY")
        self.supabase: Client = create_client(url, key)
        self.openai = OpenAI()
        self.embedding_model = "text-embedding-3-small"
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
    def create_tables(self):
        """Create the necessary tables and functions in Supabase for vector storage.
        Note: The pgvector extension must be enabled in the Supabase dashboard first."""
        try:
            # Create videos table
            self.supabase.from_("videos").select("*").limit(1).execute()
            print("Videos table exists")

            # Create transcripts table
            self.supabase.from_("transcripts").select("*").limit(1).execute()
            print("Transcripts table exists")

            # Create transcript_chunks table
            self.supabase.from_("transcript_chunks").select("*").limit(1).execute()
            print("Transcript chunks table exists")

            # Create generated_outputs table
            self.supabase.from_("generated_outputs").select("*").limit(1).execute()
            print("Generated outputs table exists")

            print("All tables exist and are accessible")
            return True
        except Exception as e:
            print(f"Error accessing tables: {e}")
            print("Please create the tables in the Supabase dashboard using the SQL editor with the following commands:")
            print("""
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create videos table
CREATE TABLE IF NOT EXISTS videos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id TEXT NOT NULL,
    collection_id TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(video_id, collection_id)
);

-- Create transcripts table
CREATE TABLE IF NOT EXISTS transcripts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id UUID REFERENCES videos(id),
    full_text TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create transcript_chunks table with vector support
CREATE TABLE IF NOT EXISTS transcript_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transcript_id UUID REFERENCES transcripts(id),
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create generated_outputs table
CREATE TABLE IF NOT EXISTS generated_outputs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id UUID REFERENCES videos(id),
    output_type TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index for similarity search
CREATE INDEX IF NOT EXISTS transcript_chunks_embedding_idx 
ON transcript_chunks 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create function for similarity search
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding vector(1536),
    match_count int DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    chunk_text TEXT,
    transcript_id UUID,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        transcript_chunks.id,
        transcript_chunks.chunk_text,
        transcript_chunks.transcript_id,
        1 - (transcript_chunks.embedding <=> query_embedding) as similarity
    FROM transcript_chunks
    ORDER BY transcript_chunks.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
""")
            return False

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
        """Split text into chunks while preserving semantic boundaries"""
        tokens = self.tokenizer.encode(text)
        chunks = []
        
        i = 0
        while i < len(tokens):
            # Get chunk of tokens
            chunk_tokens = tokens[i:i + chunk_size]
            
            # Decode chunk back to text
            chunk_text = self.tokenizer.decode(chunk_tokens)
            
            # Clean up chunk boundaries
            if i + chunk_size < len(tokens):
                # Try to break at sentence or paragraph
                last_period = chunk_text.rfind('.')
                last_newline = chunk_text.rfind('\n')
                break_point = max(last_period, last_newline)
                if break_point != -1:
                    chunk_text = chunk_text[:break_point + 1]
            
            chunks.append(chunk_text)
            
            # Move forward by chunk size minus overlap
            i += chunk_size - overlap
            
        return chunks

    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for text using OpenAI's API"""
        response = self.openai.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        return response.data[0].embedding

    def store_transcript(self, text: str, video_id: str, collection_id: str, metadata: Dict[str, Any] = None) -> str:
        """Store transcript and its chunks with embeddings"""
        try:
            # First store or get video record
            video_data = {
                "video_id": video_id,
                "collection_id": collection_id,
                "metadata": metadata or {}
            }
            video_result = self.supabase.table('videos').upsert(video_data).execute()
            video_uuid = video_result.data[0]['id']
            
            # Store full transcript
            transcript_data = {
                "video_id": video_uuid,
                "full_text": text,
                "metadata": metadata or {}
            }
            result = self.supabase.table('transcripts').insert(transcript_data).execute()
            transcript_id = result.data[0]['id']
            
            # Create and store chunks
            chunks = self.chunk_text(text)
            for i, chunk_text in enumerate(chunks):
                embedding = self.get_embedding(chunk_text)
                chunk_data = {
                    "transcript_id": transcript_id,
                    "chunk_text": chunk_text,
                    "chunk_index": i,
                    "embedding": embedding,
                    "metadata": metadata or {}
                }
                self.supabase.table('transcript_chunks').insert(chunk_data).execute()
            
            return transcript_id
            
        except Exception as e:
            print(f"Error storing transcript: {str(e)}")
            raise

    def search_similar_chunks(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for similar chunks using vector similarity"""
        query_embedding = self.get_embedding(query)
        
        # Perform similarity search using dot product
        result = self.supabase.rpc(
            'match_chunks',
            {
                'query_embedding': query_embedding,
                'match_count': limit
            }
        ).execute()
        
        return result.data 

    def store_generated_output(self, video_id: str, collection_id: str, output_type: str, content: str, metadata: Dict[str, Any] = None) -> str:
        """Store generated output (YAML config, voice prompt, etc.) for a video"""
        try:
            # First get video UUID
            video_result = self.supabase.table('videos').select('id').eq('video_id', video_id).eq('collection_id', collection_id).execute()
            if not video_result.data:
                raise ValueError(f"No video found for video_id {video_id} and collection_id {collection_id}")
            video_uuid = video_result.data[0]['id']
            
            # Store generated output
            output_data = {
                "video_id": video_uuid,
                "output_type": output_type,
                "content": content,
                "metadata": metadata or {}
            }
            result = self.supabase.table('generated_outputs').insert(output_data).execute()
            return result.data[0]['id']
            
        except Exception as e:
            print(f"Error storing generated output: {str(e)}")
            raise

    def get_generated_output(self, video_id: str, collection_id: str, output_type: str) -> Optional[str]:
        """Retrieve the most recent generated output of a specific type for a video"""
        try:
            # First get video UUID
            video_result = self.supabase.table('videos').select('id').eq('video_id', video_id).eq('collection_id', collection_id).execute()
            if not video_result.data:
                return None
            video_uuid = video_result.data[0]['id']
            
            # Get most recent output of specified type
            result = self.supabase.table('generated_outputs')\
                .select('content')\
                .eq('video_id', video_uuid)\
                .eq('output_type', output_type)\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
                
            if result.data:
                return result.data[0]['content']
            return None
            
        except Exception as e:
            print(f"Error retrieving generated output: {str(e)}")
            return None 