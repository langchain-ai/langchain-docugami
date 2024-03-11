import os

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import BaseTool

from docugami_langchain.agents import ReWOOAgent
from tests.common import (
    GENERAL_KNOWLEDGE_ANSWER_FRAGMENTS,
    GENERAL_KNOWLEDGE_QUESTION,
    RAG_ANSWER_FRAGMENTS,
    RAG_QUESTION,
    verify_response,
)


@pytest.fixture()
def fireworksai_mixtral_rewoo_agent(
    fireworksai_mixtral: BaseLanguageModel,
    huggingface_minilm: Embeddings,
    huggingface_retrieval_tool: BaseTool,
) -> ReWOOAgent:
    """
    Fireworks AI ReWOO Agent using mixtral.
    """
    agent = ReWOOAgent(
        llm=fireworksai_mixtral,
        embeddings=huggingface_minilm,
        tools=[huggingface_retrieval_tool],
    )
    return agent


@pytest.fixture()
def openai_gpt35_rewoo_agent(
    openai_gpt35: BaseLanguageModel,
    openai_ada: Embeddings,
    openai_retrieval_tool: BaseTool,
) -> ReWOOAgent:
    """
    OpenAI ReWOO Agent using GPT 3.5.
    """
    agent = ReWOOAgent(
        llm=openai_gpt35, embeddings=openai_ada, tools=[openai_retrieval_tool]
    )
    return agent


@pytest.mark.skipif(
    "FIREWORKS_API_KEY" not in os.environ, reason="Fireworks API token not set"
)
@pytest.mark.skip("Not working well with Mixtral, needs to be debugged")
def test_fireworksai_rewoo(
    fireworksai_mixtral_rewoo_agent: ReWOOAgent,
) -> None:

    # test general LLM response from agent
    response = fireworksai_mixtral_rewoo_agent.run(GENERAL_KNOWLEDGE_QUESTION)
    verify_response(response, GENERAL_KNOWLEDGE_ANSWER_FRAGMENTS)

    # test retrieval response from agent
    response = fireworksai_mixtral_rewoo_agent.run(RAG_QUESTION)
    verify_response(response, RAG_ANSWER_FRAGMENTS)


@pytest.mark.skipif(
    "OPENAI_API_KEY" not in os.environ, reason="OpenAI API token not set"
)
def test_openai_rewoo(openai_gpt35_rewoo_agent: ReWOOAgent) -> None:

    # test general LLM response from agent
    response = openai_gpt35_rewoo_agent.run(GENERAL_KNOWLEDGE_QUESTION)
    verify_response(response, GENERAL_KNOWLEDGE_ANSWER_FRAGMENTS)

    # test retrieval response from agent
    response = openai_gpt35_rewoo_agent.run(RAG_QUESTION)
    verify_response(response, RAG_ANSWER_FRAGMENTS)
