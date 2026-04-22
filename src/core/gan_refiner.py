"""
CRAVE v10.3 — GAN Refiner (Generator-Evaluator Quality Loop)
==============================================================
Two AI agents compete to produce high-quality output:

  Generator:  Writes the content based on user's request
  Evaluator:  Reads it cold against a rubric, scores it, sends fixes
  Generator:  Rewrites incorporating feedback

3 rounds. Evaluator has NO memory of previous rounds — it reads the
rubric fresh every pass. So it can't go soft. It either passes or fails.

Usage:
    from src.core.gan_refiner import refine
    result = refine(
        task="Write a business email to a client about project delays",
        rubric="Professional tone, clear timeline, empathetic but honest",
        router=model_router_instance,
        rounds=3
    )
    # result = {"final_output": "...", "rounds": 3, "scores": [6, 8, 9]}
"""

import logging
from typing import Optional, Dict

logger = logging.getLogger("crave.gan_refiner")

GENERATOR_PROMPT = """You are the GENERATOR. Your job is to write high-quality content.

TASK: {task}

{feedback_section}

Write the best possible output. Output ONLY the content itself, no meta-commentary."""

EVALUATOR_PROMPT = """You are a strict EVALUATOR. You have NEVER seen this content before. 
You must judge it FRESH against the rubric below. No leniency.

RUBRIC: {rubric}

CONTENT TO EVALUATE:
---
{content}
---

Score the content from 1-10 against the rubric.
Then list EXACTLY what is wrong and HOW to fix each issue.

Respond in this EXACT format:
SCORE: [number]
ISSUES:
- [issue 1]: [how to fix]
- [issue 2]: [how to fix]
VERDICT: [PASS if score >= 8, FAIL otherwise]"""


def refine(
    task: str,
    rubric: str,
    router,
    rounds: int = 3,
    pass_threshold: int = 8,
) -> Dict:
    """
    Run the Generator-Evaluator loop.
    
    Args:
        task: What to generate (e.g., "Write a business email about...")
        rubric: Quality criteria (e.g., "Professional tone, clear structure")
        router: ModelRouter instance for LLM calls
        rounds: Max rounds (default 3)
        pass_threshold: Score needed to pass early (default 8)
    
    Returns:
        {
            "final_output": str,
            "rounds_used": int,
            "scores": [int, ...],
            "passed": bool
        }
    """
    if not router:
        return {"final_output": "", "rounds_used": 0, "scores": [], "passed": False}

    scores = []
    current_output = ""
    feedback = ""
    passed = False

    for round_num in range(1, rounds + 1):
        logger.info(f"[GAN] Round {round_num}/{rounds}")

        # ── GENERATOR: Write or rewrite ──────────────────────────────────
        feedback_section = ""
        if feedback:
            feedback_section = (
                f"PREVIOUS ATTEMPT HAD THESE ISSUES (fix all of them):\n{feedback}\n\n"
                f"PREVIOUS OUTPUT (rewrite this, fixing all issues):\n{current_output}"
            )

        gen_prompt = GENERATOR_PROMPT.format(
            task=task,
            feedback_section=feedback_section
        )

        gen_res = router.chat(
            prompt=gen_prompt,
            system_prompt="You are a professional content generator. Write excellent content.",
            task_type="reasoning"
        )
        current_output = gen_res.get("response", "").strip()

        if not current_output:
            logger.warning(f"[GAN] Generator produced empty output in round {round_num}")
            continue

        # ── EVALUATOR: Score it cold (NO memory of previous rounds) ──────
        eval_prompt = EVALUATOR_PROMPT.format(
            rubric=rubric,
            content=current_output
        )

        eval_res = router.chat(
            prompt=eval_prompt,
            system_prompt="You are a strict quality evaluator. Judge content against the rubric.",
            task_type="reasoning"
        )
        eval_text = eval_res.get("response", "")

        # Parse score
        score = _extract_score(eval_text)
        scores.append(score)
        logger.info(f"[GAN] Round {round_num} score: {score}/10")

        # Check if passed
        if score >= pass_threshold:
            passed = True
            logger.info(f"[GAN] PASSED at round {round_num} with score {score}")
            break

        # Extract feedback for next round
        feedback = eval_text

    return {
        "final_output": current_output,
        "rounds_used": len(scores),
        "scores": scores,
        "passed": passed,
    }


def _extract_score(eval_text: str) -> int:
    """Extract numeric score from evaluator output."""
    for line in eval_text.split("\n"):
        line = line.strip().upper()
        if line.startswith("SCORE:"):
            try:
                num_str = line.replace("SCORE:", "").strip()
                # Handle "8/10" and "8" formats
                num_str = num_str.split("/")[0].strip()
                return int(float(num_str))
            except (ValueError, IndexError):
                continue
    return 5  # Default if parsing fails
