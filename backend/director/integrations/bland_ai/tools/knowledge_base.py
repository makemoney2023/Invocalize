"""
Knowledge Base Tool for managing Bland AI vector knowledge bases
"""

from typing import Dict, List, Optional, Any
import logging
from datetime import datetime
import os

from director.core.config import Config
from director.integrations.bland_ai.service import BlandAIService
from director.utils.supabase import SupabaseVectorStore

logger = logging.getLogger(__name__)

class KnowledgeBaseTool:
    """Tool for managing Bland AI vector knowledge bases"""
    
    def __init__(self, config: Config):
        """Initialize the knowledge base tool
        
        Args:
            config: Director configuration object
        """
        self.config = config
        self.bland_ai_service = BlandAIService(config)
        self.supabase = SupabaseVectorStore()
        
    def create_from_analysis(self, analysis_data: str, name: Optional[str] = None, analysis_id: Optional[str] = None, video_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a new knowledge base from sales analysis data
        
        Args:
            analysis_data: Raw analysis text to use for knowledge base
            name: Optional name for the knowledge base. If not provided, will generate one
            analysis_id: Optional ID of the analysis used to create the knowledge base
            video_id: Optional ID of the video associated with the analysis
            
        Returns:
            Dictionary containing knowledge base metadata including ID
        """
        try:
            # Generate name if not provided
            if not name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name = f"Sales Analysis KB - {timestamp}"
                
            # Validate analysis text
            if not analysis_data or analysis_data == 'None' or isinstance(analysis_data, type(None)):
                raise ValueError("No valid analysis text found")
                
            # Create description
            description = f"Knowledge base created from sales analysis"
            
            # Create knowledge base through service with raw analysis text
            kb_result = self.bland_ai_service.create_knowledge_base(
                name=name,
                description=description,
                content=analysis_data
            )
            
            # Store metadata in Supabase
            if kb_result and "vector_id" in kb_result:
                metadata = {
                    "created_at": datetime.now().isoformat(),
                    "source": "analysis"
                }
                self.supabase.store_bland_ai_knowledge_base(
                    kb_id=kb_result["vector_id"],
                    analysis_id=analysis_id,
                    video_id=video_id,
                    name=name,
                    description=description,
                    metadata=metadata
                )
            
            return kb_result
            
        except Exception as e:
            logger.error(f"Failed to create knowledge base from analysis: {str(e)}", exc_info=True)
            raise
            
    def create_from_file(self, file_path: str, name: Optional[str] = None, description: Optional[str] = None) -> Dict[str, Any]:
        """Create a new knowledge base from a file
        
        Args:
            file_path: Path to the file (.pdf, .txt, .doc, or .docx)
            name: Optional name for the knowledge base
            description: Optional description for the knowledge base
            
        Returns:
            Dictionary containing knowledge base metadata
        """
        try:
            if not os.path.exists(file_path):
                raise ValueError(f"File not found: {file_path}")
                
            # Generate name if not provided
            if not name:
                file_name = os.path.basename(file_path)
                name = f"KB from {file_name}"
                
            # Create knowledge base through service
            kb_result = self.bland_ai_service.upload_knowledge_base_file(
                file_path=file_path,
                name=name,
                description=description
            )
            
            # Store metadata in Supabase
            if kb_result and "vector_id" in kb_result:
                metadata = {
                    "created_at": datetime.now().isoformat(),
                    "source": "file",
                    "file_name": os.path.basename(file_path)
                }
                self.supabase.store_bland_ai_knowledge_base(
                    kb_id=kb_result["vector_id"],
                    analysis_id=None,
                    video_id=None,
                    name=name,
                    description=description,
                    metadata=metadata
                )
            
            return kb_result
            
        except Exception as e:
            logger.error(f"Failed to create knowledge base from file: {str(e)}", exc_info=True)
            raise
            
    def link_to_pathway(self, kb_id: str, pathway_id: str) -> None:
        """Link a knowledge base to a conversation pathway
        
        Args:
            kb_id: ID of the knowledge base
            pathway_id: ID of the pathway to link to
        """
        try:
            # Get knowledge base metadata
            kb_metadata = self.supabase.get_bland_ai_knowledge_base(kb_id)
            if not kb_metadata:
                raise ValueError(f"Knowledge base {kb_id} not found")
                
            # Get or create pathway metadata
            pathway_metadata = self.supabase.get_bland_ai_pathway(pathway_id)
            if not pathway_metadata:
                # Create pathway record if it doesn't exist
                self.supabase.store_bland_ai_pathway(
                    pathway_id=pathway_id,
                    name=f"Pathway {pathway_id}",
                    description="Automatically created pathway record",
                    metadata={
                        "created_at": datetime.now().isoformat(),
                        "source": "link_to_pathway"
                    }
                )
            
            # Update knowledge base metadata to include pathway link
            kb_metadata = kb_metadata.get("metadata", {})
            kb_metadata["linked_pathways"] = kb_metadata.get("linked_pathways", [])
            if pathway_id not in kb_metadata["linked_pathways"]:
                kb_metadata["linked_pathways"].append(pathway_id)
                
            # Update knowledge base record
            self.supabase.store_bland_ai_knowledge_base(
                kb_id=kb_id,
                analysis_id=kb_metadata.get("analysis_id"),
                video_id=kb_metadata.get("video_id"),
                name=kb_metadata.get("name"),
                description=kb_metadata.get("description"),
                metadata=kb_metadata
            )
            
        except Exception as e:
            logger.error(f"Failed to link knowledge base to pathway: {str(e)}")
            raise
            
    def get_pathway_knowledge_bases(self, pathway_id: str) -> List[Dict[str, Any]]:
        """Get all knowledge bases linked to a pathway
        
        Args:
            pathway_id: ID of the pathway
            
        Returns:
            List of knowledge base metadata dictionaries
        """
        try:
            # Query knowledge bases with pathway in linked_pathways metadata
            result = self.supabase.table('bland_ai_knowledge_bases')\
                .select('*')\
                .execute()
                
            knowledge_bases = []
            for kb in result.data:
                metadata = kb.get("metadata", {})
                linked_pathways = metadata.get("linked_pathways", [])
                if pathway_id in linked_pathways:
                    knowledge_bases.append(kb)
                    
            return knowledge_bases
            
        except Exception as e:
            logger.error(f"Failed to get pathway knowledge bases: {str(e)}", exc_info=True)
            return []
            
    def update_from_analysis(self, kb_id: str, analysis_data: str, name: Optional[str] = None, description: Optional[str] = None) -> Dict[str, Any]:
        """Update an existing knowledge base with new analysis data
        
        Args:
            kb_id: ID of the knowledge base to update
            analysis_data: New analysis text
            name: Optional new name for the knowledge base
            description: Optional new description for the knowledge base
            
        Returns:
            Updated knowledge base metadata
        """
        try:
            # Get existing KB metadata
            existing_kb = self.supabase.get_bland_ai_knowledge_base(kb_id)
            if not existing_kb:
                raise ValueError(f"Knowledge base {kb_id} not found")
                
            # Use existing name/description if not provided
            name = name or existing_kb.get("name")
            description = description or existing_kb.get("description")
            
            # Update through service
            kb_result = self.bland_ai_service.update_knowledge_base(
                kb_id=kb_id,
                name=name,
                description=description,
                content=analysis_data
            )
            
            # Update metadata in Supabase
            if kb_result and "vector_id" in kb_result:
                metadata = existing_kb.get("metadata", {})
                metadata["updated_at"] = datetime.now().isoformat()
                self.supabase.store_bland_ai_knowledge_base(
                    kb_id=kb_id,
                    analysis_id=existing_kb.get("analysis_id"),
                    video_id=existing_kb.get("video_id"),
                    name=name,
                    description=description,
                    metadata=metadata
                )
            
            return kb_result
            
        except Exception as e:
            logger.error(f"Failed to update knowledge base: {str(e)}", exc_info=True)
            raise
            
    def get_knowledge_base(self, kb_id: str, include_text: bool = False) -> Optional[Dict[str, Any]]:
        """Get details for a specific knowledge base
        
        Args:
            kb_id: ID of the knowledge base
            include_text: Whether to include the full text content
            
        Returns:
            Knowledge base metadata and optionally content, or None if not found
        """
        try:
            # Get metadata from Supabase
            kb_metadata = self.supabase.get_bland_ai_knowledge_base(kb_id)
            
            if not kb_metadata:
                return None
                
            # Get content from Bland AI if requested
            if include_text:
                kb_content = self.bland_ai_service.get_knowledge_base(kb_id, include_text)
                if kb_content:
                    kb_metadata["content"] = kb_content.get("content")
                    
            return kb_metadata
            
        except Exception as e:
            logger.error(f"Failed to get knowledge base details: {str(e)}", exc_info=True)
            return None
            
    def list_knowledge_bases(self, include_text: bool = False) -> List[Dict[str, Any]]:
        """List all knowledge bases
        
        Args:
            include_text: Whether to include the full text content
            
        Returns:
            List of knowledge base metadata dictionaries
        """
        try:
            # Get all knowledge bases from Supabase
            result = self.supabase.table('bland_ai_knowledge_bases')\
                .select('*')\
                .order('created_at', desc=True)\
                .execute()
                
            knowledge_bases = result.data
            
            # Get content from Bland AI if requested
            if include_text:
                for kb in knowledge_bases:
                    kb_id = kb.get("kb_id")
                    if kb_id:
                        kb_content = self.bland_ai_service.get_knowledge_base(kb_id, include_text)
                        if kb_content:
                            kb["content"] = kb_content.get("content")
                            
            return knowledge_bases
            
        except Exception as e:
            logger.error(f"Failed to list knowledge bases: {str(e)}", exc_info=True)
            return []
            
    def query(self, kb_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Query a knowledge base using vector similarity search
        
        Args:
            kb_id: ID of the knowledge base to query
            query: Query text to search for
            top_k: Number of results to return
            
        Returns:
            List of matching knowledge base entries
        """
        try:
            return self.bland_ai_service.query_knowledge_base(kb_id, query, top_k)
        except Exception as e:
            logger.error(f"Failed to query knowledge base: {str(e)}", exc_info=True)
            return [] 