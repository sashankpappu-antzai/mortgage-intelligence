"""DeepEval LLM evaluation tests for mortgage-intelligence.

Run these evals with:
    uv run deepeval test run backend/tests/evals/

To log results to Confident AI (Deepeval's platform), set DEEPEVAL_API_KEY
in your environment and run:
    uv run deepeval login
    uv run deepeval test run backend/tests/evals/
"""

import pytest
from deepeval import assert_test
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
)
from deepeval.test_case import LLMTestCase

# ── Metrics ───────────────────────────────────────────────────────────────────
# Adjust thresholds to match your team's quality bar.

answer_relevancy = AnswerRelevancyMetric(threshold=0.7, model="gpt-4o", include_reason=True)
faithfulness = FaithfulnessMetric(threshold=0.7, model="gpt-4o", include_reason=True)
contextual_precision = ContextualPrecisionMetric(threshold=0.7, model="gpt-4o")
contextual_recall = ContextualRecallMetric(threshold=0.7, model="gpt-4o")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_case(
    input: str,
    actual_output: str,
    expected_output: str = "",
    retrieval_context: list[str] | None = None,
) -> LLMTestCase:
    """Build an LLMTestCase with optional RAG context."""
    return LLMTestCase(
        input=input,
        actual_output=actual_output,
        expected_output=expected_output,
        retrieval_context=retrieval_context or [],
    )


# ── Example eval tests ────────────────────────────────────────────────────────
# Replace the placeholder inputs/outputs below with calls to your actual agent.
# Import and invoke your agent here, e.g.:
#
#   from backend.agents.base_agent import MyAgent
#   agent = MyAgent()
#   result = await agent.run(input=question, session_id="eval-session")


@pytest.mark.parametrize(
    "question,expected_answer",
    [
        (
            "What is mortgage-intelligence?",
            "mortgage-intelligence is an agentic application.",
        ),
    ],
)
def test_answer_relevancy(question: str, expected_answer: str) -> None:
    """Verify that agent responses are relevant to the question asked."""
    # TODO: replace with your actual agent call
    actual_output = expected_answer  # placeholder — wire in real agent output

    test_case = _make_case(
        input=question,
        actual_output=actual_output,
        expected_output=expected_answer,
    )
    assert_test(test_case, [answer_relevancy])


@pytest.mark.parametrize(
    "question,context,expected_answer",
    [
        (
            "Summarise the key points from the context.",
            ["mortgage-intelligence uses FastAPI and is deployed via Docker Compose."],
            "mortgage-intelligence uses FastAPI and Docker Compose.",
        ),
    ],
)
def test_faithfulness(question: str, context: list[str], expected_answer: str) -> None:
    """Verify that RAG-grounded responses do not hallucinate beyond the context."""
    # TODO: replace with your actual RAG pipeline output
    actual_output = expected_answer  # placeholder — wire in real agent output

    test_case = _make_case(
        input=question,
        actual_output=actual_output,
        expected_output=expected_answer,
        retrieval_context=context,
    )
    assert_test(test_case, [faithfulness])


@pytest.mark.parametrize(
    "question,context,expected_answer",
    [
        (
            "Which framework does mortgage-intelligence use for agents?",
            [
                "mortgage-intelligence uses the langchain framework for agent orchestration.",
                "The application is built with FastAPI.",
            ],
            "langchain",
        ),
    ],
)
def test_contextual_precision_and_recall(
    question: str, context: list[str], expected_answer: str
) -> None:
    """Verify retrieval quality — only relevant chunks are surfaced."""
    # TODO: replace with your actual retrieval pipeline output
    actual_output = expected_answer  # placeholder

    test_case = _make_case(
        input=question,
        actual_output=actual_output,
        expected_output=expected_answer,
        retrieval_context=context,
    )
    assert_test(test_case, [contextual_precision, contextual_recall])
