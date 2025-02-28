import pytest
from unittest.mock import Mock, patch, call, MagicMock
from datetime import datetime
import json
import logging

from director.agents.sales_prompt_extractor import SalesPromptExtractorAgent
from director.core.session import Session, OutputMessage, RoleTypes, MsgStatus, TextContent
from director.llm.videodb_proxy import VideoDBProxy, VideoDBProxyConfig
from director.llm.anthropic import AnthropicAI, AnthropicAIConfig
from director.agents.base import AgentStatus
from director.tools.anthropic_tool import AnthropicTool
from director.llm.openai import OpenaiConfig, OpenAIChatModel, OpenAI

# Sample test data
SAMPLE_TRANSCRIPT = """
In this sales training, we use the SPIN selling technique. First, ask Situation questions
to understand the customer's context. Then, Problem questions to uncover issues.
When handling price objections, always focus on value over cost.
Remember to use active listening and mirror the customer's language.
Close with a summary of benefits and clear next steps.
"""

SAMPLE_ANALYSIS = {
    "raw_analysis": SAMPLE_TRANSCRIPT,
    "structured_data": {
        "sales_techniques": [{
            "name": "SPIN Selling",
            "description": "Systematic approach using situation, problem, implication, and need-payoff questions",
            "examples": ["First, ask Situation questions"],
            "context": "Initial customer engagement"
        }],
        "communication_strategies": [{
            "type": "Active Listening",
            "description": "Pay attention and mirror customer's language",
            "application": "Throughout the conversation"
        }],
        "objection_handling": [{
            "objection_type": "Price concerns",
            "recommended_response": "Focus on value over cost",
            "examples": ["When handling price objections"]
        }],
        "closing_techniques": [{
            "name": "Benefit Summary Close",
            "description": "Summarize key benefits and establish next steps",
            "effectiveness": "When customer shows interest but needs final push"
        }]
    },
    "metadata": {
        "sections_found": ["sales_techniques", "communication_strategies", "objection_handling", "closing_techniques"],
        "total_techniques": 4
    }
}

@pytest.fixture
def mock_session():
    session = Mock(spec=Session)
    session.session_id = "test_session_id"
    session.conv_id = "test_conv_id"
    session.db = None
    session.output_message = Mock(spec=OutputMessage)
    session.output_message.push_update = Mock()
    session.output_message.content = []
    session.output_message.actions = []
    session.created_at = datetime.now()
    session.collection_id = "test_collection"
    return session

@pytest.fixture
def mock_output_message():
    output_message = Mock(spec=OutputMessage)
    output_message.content = []
    output_message.actions = []
    output_message.push_update = Mock()
    output_message.publish = Mock()
    return output_message

@pytest.fixture
def mock_config():
    return VideoDBProxyConfig(
        api_key="test_key",
        api_base="https://api.videodb.io",
        llm_type="videodb_proxy"
    )

@pytest.fixture
def mock_llm(mock_config):
    llm = Mock(spec=VideoDBProxy)
    llm.api_key = mock_config.api_key
    llm.api_base = mock_config.api_base
    return llm

@pytest.fixture
def mock_anthropic_config():
    config = MagicMock(spec=AnthropicAIConfig)
    config.api_key = "test_anthropic_key"
    config.api_base = "https://api.anthropic.com"
    config.llm_type = "anthropic"
    config.chat_model = "claude-3-opus-20240229"
    config.temperature = 0.7
    config.top_p = 1.0
    config.max_tokens = 4096
    config.timeout = 30
    config.enable_langfuse = False
    return config

@pytest.fixture
def mock_anthropic(mock_anthropic_config):
    llm = MagicMock(spec=AnthropicAI)
    llm.api_key = mock_anthropic_config.api_key
    llm.api_base = mock_anthropic_config.api_base
    llm.chat_model = mock_anthropic_config.chat_model
    llm.temperature = mock_anthropic_config.temperature
    llm.top_p = mock_anthropic_config.top_p
    llm.max_tokens = mock_anthropic_config.max_tokens
    llm.timeout = mock_anthropic_config.timeout
    llm.enable_langfuse = mock_anthropic_config.enable_langfuse
    return llm

@pytest.fixture
def mock_logger():
    return Mock(spec=logging.Logger)

@pytest.fixture
def mock_anthropic_tool():
    mock = Mock()
    mock.api_key = "test_key"
    mock.chat_completions = Mock()
    return mock

@pytest.fixture
def mock_openai_config():
    config = MagicMock(spec=OpenaiConfig)
    config.api_key = "test_openai_key"
    config.chat_model = OpenAIChatModel.GPT4o
    config.max_tokens = 4096
    return config

@pytest.fixture
def mock_openai():
    mock = MagicMock(spec=OpenAI)
    mock.api_key = "test_openai_key"
    mock.chat_completions = Mock()
    return mock

@pytest.fixture
def agent(mock_session, mock_llm, mock_config, mock_anthropic, mock_anthropic_config, mock_anthropic_tool, mock_openai_config, mock_openai):
    with patch('director.llm.get_default_llm', return_value=mock_llm), \
         patch('director.llm.videodb_proxy.VideoDBProxyConfig', return_value=mock_config), \
         patch('director.llm.anthropic.AnthropicAI', return_value=mock_anthropic), \
         patch('director.llm.anthropic.AnthropicAIConfig', return_value=mock_anthropic_config), \
         patch('director.llm.openai.OpenaiConfig', return_value=mock_openai_config), \
         patch('director.llm.openai.OpenAI', return_value=mock_openai):
        agent = SalesPromptExtractorAgent(
            session=mock_session,
            analysis_llm=mock_anthropic_tool,
            openai_config=mock_openai_config,
            conversation_llm=mock_openai
        )
        # Mock the push_status_update method to properly handle status updates
        agent.push_status_update = Mock()
        agent.output_message.push_update.call_args_list = []
        return agent

def test_get_transcript(agent):
    """Test transcript retrieval"""
    # Mock transcription agent response
    mock_response = Mock(status=AgentStatus.SUCCESS)
    mock_response.data = {"transcript": SAMPLE_TRANSCRIPT}
    agent.transcription_agent.run = Mock(return_value=mock_response)
    
    transcript = agent._get_transcript("test_video_id")
    assert transcript.strip() == SAMPLE_TRANSCRIPT.strip()

def test_analyze_content_status_updates(agent):
    """Test that analyze_content properly updates status"""
    # Mock the LLM response
    mock_llm_response = Mock()
    mock_llm_response.content = json.dumps(SAMPLE_ANALYSIS["structured_data"])
    agent.analysis_llm.chat_completions = Mock(return_value=mock_llm_response)
    
    # Mock status update
    status_update = Mock()
    status_update.status_message = "Test status"
    agent.output_message.push_update = Mock(return_value=None)
    agent.output_message.push_update.call_args_list = [((status_update,),)]
    
    # Call analyze_content
    agent.analyze_content(SAMPLE_TRANSCRIPT, "full")
    
    # Verify status updates were called
    assert agent.output_message.push_update.called

def test_generate_prompt_status_updates(agent):
    """Test that generate_prompt properly updates status"""
    # Mock the LLM responses
    mock_system_response = Mock()
    mock_system_response.content = "Test system prompt"
    
    mock_conv_response = Mock()
    mock_conv_response.content = json.dumps([{
        "title": "Test Conversation",
        "conversation": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]
    }])
    
    # Setup the mock to return different responses
    agent.analysis_llm.chat_completions = Mock(side_effect=[
        mock_system_response,
        mock_conv_response
    ])
    
    # Mock status update
    status_update = Mock()
    status_update.status_message = "Test status"
    agent.output_message.push_update = Mock(return_value=None)
    agent.output_message.push_update.call_args_list = [((status_update,),)]
    
    # Call generate_prompt
    result = agent.generate_prompt(SAMPLE_ANALYSIS)
    
    # Verify status updates were called
    assert agent.output_message.push_update.called

def test_error_handling_with_status(agent):
    """Test error handling with proper status updates"""
    # Mock the LLM to raise an exception
    agent.analysis_llm.chat_completions = Mock(side_effect=Exception("API Error"))
    
    # Mock status update
    status_update = Mock()
    status_update.status = MsgStatus.error
    status_update.status_message = "Error in analysis"
    agent.output_message.push_update = Mock(return_value=None)
    agent.output_message.push_update.call_args_list = [((status_update,),)]
    
    # Call analyze_content and expect it to fail
    with pytest.raises(Exception):
        agent.analyze_content(SAMPLE_TRANSCRIPT, "full")
    
    # Verify error status was sent
    assert agent.output_message.push_update.called

def test_conversation_parsing_fallback(agent):
    """Test the fallback mechanism for conversation parsing"""
    # Mock the LLM to return invalid JSON
    mock_response = Mock()
    mock_response.content = "Invalid JSON content"
    agent.analysis_llm.chat_completions = Mock(return_value=mock_response)
    
    # Call generate_prompt
    result = agent.generate_prompt(SAMPLE_ANALYSIS)
    
    # Verify fallback conversation was used
    assert len(result["example_conversations"]) == 1
    assert result["example_conversations"][0]["title"] == "Basic Sales Conversation"
    assert len(result["example_conversations"][0]["conversation"]) == 2

def test_full_workflow(agent, mock_output_message):
    """Test the complete workflow"""
    # Mock all dependent functions
    agent._get_transcript = Mock(return_value=SAMPLE_TRANSCRIPT)
    agent.analyze_content = Mock(return_value=SAMPLE_ANALYSIS)
    agent.generate_prompt = Mock(return_value={
        "system_prompt": "Test prompt",
        "first_message": "Hello",
        "example_conversations": [],
        "metadata": {}
    })
    
    # Set up output message
    agent.output_message = mock_output_message
    
    # Run the agent
    response = agent.run("test_video_id")
    assert response.status == AgentStatus.SUCCESS

def test_structure_analysis_json(mock_session, mock_llm, mock_config, mock_anthropic, mock_anthropic_config, mock_logger, mock_anthropic_tool, mock_openai_config, mock_openai, mock_output_message):
    """Test structured analysis output"""
    with patch('director.llm.get_default_llm', return_value=mock_llm), \
         patch('director.llm.videodb_proxy.VideoDBProxyConfig', return_value=mock_config), \
         patch('director.llm.anthropic.AnthropicAI', return_value=mock_anthropic), \
         patch('director.llm.anthropic.AnthropicAIConfig', return_value=mock_anthropic_config), \
         patch('director.agents.sales_prompt_extractor.logger', mock_logger), \
         patch('director.llm.openai.OpenaiConfig', return_value=mock_openai_config), \
         patch('director.llm.openai.OpenAI', return_value=mock_openai):
        agent = SalesPromptExtractorAgent(
            mock_session,
            analysis_llm=mock_anthropic_tool,
            openai_config=mock_openai_config,
            conversation_llm=mock_openai
        )

        # Mock the analysis response
        mock_analysis = {
            "structured_data": {
                "sales_techniques": [{"name": "Test Technique", "description": "Test description"}],
                "communication_strategies": [{"type": "Test Strategy", "description": "Test strategy description"}],
                "objection_handling": [{"objection_type": "Test Objection", "recommended_response": "Test response"}],
                "closing_techniques": [{"name": "Test Close", "description": "Test closing description"}]
            },
            "raw_analysis": "Test raw analysis",
            "metadata": {
                "sections_found": ["sales_techniques"],
                "total_techniques": 1
            }
        }

        # Mock all required methods
        agent._get_transcript = Mock(return_value=SAMPLE_TRANSCRIPT)
        agent.analyze_content = Mock(return_value=mock_analysis)
        agent.generate_prompt = Mock(return_value={
            "system_prompt": "Test prompt",
            "first_message": "Hello",
            "example_conversations": [],
            "metadata": {}
        })

        # Set up output message
        agent.output_message = mock_output_message

        # Run the test with structured output format
        response = agent.run("test_video_id", analysis_type="sales_techniques", output_format="structured")

        # Verify the response
        assert response.status == AgentStatus.SUCCESS
        assert isinstance(response.data, dict)
        assert "analysis" in response.data
        assert "sales_techniques" in response.data["analysis"]
        assert len(response.data["analysis"]["sales_techniques"]) == 1
        assert response.data["analysis"]["sales_techniques"][0]["name"] == "Test Technique"
        assert response.data["analysis"]["sales_techniques"][0]["description"] == "Test description"

def test_structure_analysis_fallback(mock_session, mock_llm, mock_config, mock_anthropic, mock_anthropic_config, mock_logger, mock_anthropic_tool, mock_openai_config, mock_openai, mock_output_message):
    """Test analysis fallback behavior"""
    with patch('director.llm.get_default_llm', return_value=mock_llm), \
         patch('director.llm.videodb_proxy.VideoDBProxyConfig', return_value=mock_config), \
         patch('director.llm.anthropic.AnthropicAI', return_value=mock_anthropic), \
         patch('director.llm.anthropic.AnthropicAIConfig', return_value=mock_anthropic_config), \
         patch('director.agents.sales_prompt_extractor.logger', mock_logger), \
         patch('director.llm.openai.OpenaiConfig', return_value=mock_openai_config), \
         patch('director.llm.openai.OpenAI', return_value=mock_openai):
        agent = SalesPromptExtractorAgent(
            mock_session,
            analysis_llm=mock_anthropic_tool,
            openai_config=mock_openai_config,
            conversation_llm=mock_openai
        )
        
        # Mock an invalid analysis response that will fail JSON parsing
        agent.analyze_content = Mock(side_effect=json.JSONDecodeError("Failed to parse", "{", 0))
        agent._get_transcript = Mock(return_value=SAMPLE_TRANSCRIPT)
        
        # Set up output message
        agent.output_message = mock_output_message
        
        response = agent.run("test_video_id")
        assert response.status == AgentStatus.ERROR
        # Check that the error message contains the JSON parse error
        assert "Failed to parse" in response.message 