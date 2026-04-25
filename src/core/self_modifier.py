"""
CRAVE — Code Self-Modifier (Self-Evolution Engine)
Save to: D:\\CRAVE\\src\\core\\self_modifier.py

Safely modify the codebase using a multi-model consensus approach.
Generates code, runs it in an isolated sandbox, previews diff to user,
and merges only on explicit dual-channel approval.
"""

import os
import sys
import json
import logging
import concurrent.futures
import ast
from datetime import datetime

logger = logging.getLogger("crave.core.self_modifier")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


class SelfModifier:
    """Manages autonomous codebase modifications safely."""

    def __init__(self):
        self._load_dependencies()
        self._session_attempts = 0

    def _load_dependencies(self):
        """Lazy load to avoid cyclic imports."""
        from src.core.model_router import ModelRouter
        from src.core.sandbox_runner import SandboxRunner
        from src.core.git_safety import GitSafety
        from src.security.confirmation_gate import get_confirmation_gate

        self.router = ModelRouter()
        self.sandbox = SandboxRunner()
        self.git = GitSafety()
        self.gate = get_confirmation_gate()

    def _get_best_coders(self) -> list[tuple[str, str]]:
        """
        Return the top 2 available coding models for consensus.
        Priority: Gemini 3.1 Pro / 2.5 Pro > Claude > OpenAI > Groq > Local
        """
        available = []
        
        # 1. Gemini
        if self.router.gemini_client:
            # We assume model_router config has gemini pointing to latest 
            # (you mentioned Gemini 3.1 Pro / Gemini-latest)
            gemini_model = self.router._api_models.get("gemini", "gemini-2.0-flash")
            available.append(("gemini", gemini_model))
            
        # 2. Claude / Anthropic (if configured via OpenRouter or native)
        if "ANTHROPIC_API_KEY" in os.environ:
            available.append(("claude", "claude-3-7-sonnet-20250219"))
            
        # 3. OpenAI
        if "OPENAI_API_KEY" in os.environ:
             available.append(("openai", "gpt-4o"))
             
        # 4. Groq
        if self.router.groq_client:
             available.append(("groq", "deepseek-r1-distill-llama-70b"))
             
        # 5. Local
        local_model = self.router._models.get("reasoning", "qwen3:8b")
        available.append(("local", local_model))

        # Return top 2 distinct models
        if len(available) >= 2:
            return available[:2]
        elif len(available) == 1:
            return [available[0], available[0]] # Use same model twice if only 1 exists
        else:
            return [("local", "qwen3:8b"), ("local", "qwen3:8b")]

    def _call_model(self, provider: str, model_name: str, prompt: str) -> str:
        """Call a specific model using ModelRouter's internal methods."""
        msgs = [{"role": "user", "content": prompt}]
        try:
            if provider == "gemini":
                return self.router._call_gemini(model_name, msgs)
            elif provider == "claude" or provider == "openai":
                # Assuming OpenRouter handles these 
                return self.router._call_openrouter(model_name, msgs)
            elif provider == "groq":
                return self.router._call_groq(model_name, msgs)
            else:
                return self.router._call_ollama(model_name, msgs)
        except Exception as e:
            logger.error(f"[SelfModifier] Model {model_name} failed: {e}")
            return ""

    def _generate_code_consensus(self, task_description: str) -> list[dict]:
        """
        Execute multi-model consensus to generate code changes.
        Returns a list of dicts: [{"file": "path", "content": "..."}]
        """
        models = self._get_best_coders()
        logger.info(f"[SelfModifier] Using models for consensus: {models}")

        prompt = f"""You are the CRAVE Self-Evolution Engine.
Your task is to modify the codebase to implement this feature:
{task_description}

System architecture:
- D:\\CRAVE\\src\\core\\ (orchestrator, router, etc)
- D:\\CRAVE\\src\\agents\\ (task specific tools)
- D:\\CRAVE\\src\\security\\ (rbac, face_id)
- D:\\CRAVE\\config\\ (json settings)

Return ONLY a JSON array of file edits. DO NOT return the entire file content. Use `search` and `replace` block diffs.
Format:
[
  {{ "file": "src/core/orchestrator.py", "type": "edit", "search": "def old_function():\\n    pass", "replace": "def new_function():\\n    return True" }},
  {{ "file": "src/agents/new_agent.py", "type": "create", "content": "import os\\n..." }}
]
Respond with valid JSON only."""

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_to_model = {
                executor.submit(self._call_model, p, m, prompt): f"{p}-{m}" 
                for p, m in models
            }
            for future in concurrent.futures.as_completed(future_to_model):
                try:
                    res = future.result()
                    # Clean markdown formatting if present
                    if "```json" in res:
                        res = res.split("```json")[1].split("```")[0].strip()
                    elif "```" in res:
                        res = res.split("```")[1].strip()
                    
                    parsed = json.loads(res)
                    if isinstance(parsed, list):
                        results.append(parsed)
                except Exception as e:
                    logger.error(f"[SelfModifier] Consensus parsing error: {e}")

        # Basic consensus logic: if we got multiple successful responses, pick the first one for now.
        # Adv: send both to a judge model to pick the best. 
        if not results:
            raise ValueError("All code generation models failed to return valid JSON.")

        # If we have 2 distinct results, ask Gemini to pick the best one
        if len(results) >= 2 and self.router.gemini_client:
             try:
                 judge_prompt = f"Which JSON code implementation is better for: {task_description}?\nReturn only '1' or '2'."
                 judge_res = self._call_model("gemini", models[0][1], judge_prompt)
                 if "2" in judge_res:
                     return results[1]
             except:
                 pass

        return results[0]

    def _verify_ast(self, modifications: list[dict]) -> tuple[bool, str]:
        """Statically analyze generated code for dangerous patterns."""
        for mod in modifications:
            content = mod.get("content", mod.get("replace", ""))
            if not content:
                continue
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.While):
                        # Detect `while True:` loops
                        if isinstance(node.test, ast.Constant) and node.test.value is True:
                            return False, f"AST Error: Unsafe 'while True:' loop detected in {mod.get('file')}"
                    elif isinstance(node, ast.Call):
                        # Detect dangerous OS calls
                        if isinstance(node.func, ast.Attribute):
                            if node.func.attr in ["system", "popen", "rmtree"]:
                                return False, f"AST Error: Potentially dangerous OS call '{node.func.attr}' in {mod.get('file')}"
            except SyntaxError:
                return False, f"AST Error: Generated code has invalid Python syntax in {mod.get('file')}"
        return True, "AST check passed"

    def execute_modification(self, task_description: str) -> str:
        """
        The massive lifecycle workflow for self-modification:
        1. Parse task & generate code consensus
        2. Git checkpoint + branch
        3. Sandbox venv test
        4. User confirmation Diff
        5. Merge + auto-revert monitor
        """
        if self._session_attempts >= 3:
            return "Safety Halt: Reached maximum self-modification attempts (3) for this session. Please review system stability."
            
        self._session_attempts += 1
        logger.info(f"[SelfModifier] Starting modification: {task_description} (Attempt {self._session_attempts}/3)")
        
        feature_slug = "".join([c if c.isalnum() else "-" for c in task_description[:20].lower()])
        branch_name = f"feat/{feature_slug}-{int(datetime.now().timestamp())}"

        # 1. Generate core code
        try:
            logger.info("[SelfModifier] 🧠 Generating code consensus...")
            modifications = self._generate_code_consensus(task_description)
            if not modifications:
                return "Failed to generate valid code."
        except Exception as e:
            return f"Code generation failed: {e}"

        # 2. Git Checkpoint
        if not self.git.is_repo():
            self.git.init_repo()
            
        base_commit = self.git.checkpoint(f"Pre-modification state for: {task_description}")
        if not self.git.create_branch(branch_name):
            return "Failed to create safety branch."

        # 2.5 GAN Refinement — improve generated code before testing
        try:
            from src.core.gan_refiner import refine as gan_refine
            if self._router:
                for mod in modifications:
                    code = mod.get("code", "")
                    if code and len(code) > 50:
                        gan_result = gan_refine(
                            task=f"Improve this Python code for: {task_description}\n\n{code}",
                            rubric="Correct Python syntax, no while True loops, no dangerous OS calls, handles edge cases, clean style",
                            router=self._router,
                            rounds=2,
                            pass_threshold=7,
                        )
                        if gan_result.get("passed") and gan_result.get("final_output"):
                            mod["code"] = gan_result["final_output"]
                            logger.info(f"[SelfModifier] GAN refined {mod.get('file')} (scores: {gan_result['scores']})")
        except Exception as e:
            logger.debug(f"[SelfModifier] GAN refinement skipped: {e}")

        # 2.6 AST Safety Check
        logger.info("[SelfModifier] 🔍 Running AST static analysis...")
        ast_ok, ast_msg = self._verify_ast(modifications)
        if not ast_ok:
            return f"Code Generation Rejected: {ast_msg}"

        # 3. Sandbox Testing
        logger.info("[SelfModifier] 🧪 Setting up isolated sandbox...")
        if not self.sandbox.setup_sandbox(branch_name):
            self.git.delete_branch(branch_name)
            return "Failed to create sandbox environment."

        logger.info("[SelfModifier] 🧪 Applying code to sandbox...")
        if not self.sandbox.apply_code_changes(branch_name, modifications):
            self.git.delete_branch(branch_name)
            self.sandbox.cleanup(branch_name)
            return "Failed to safely apply code changes to sandbox."

        # Detect new dependencies (naive check for this phase)
        # Assuming model didn't provide requirements modifications, we just run
        logger.info("[SelfModifier] 🧪 Running sandbox smoke tests...")
        tests_passed, test_output = self.sandbox.run_smoke_tests(branch_name)

        # 4. Generate Diff Report
        output_report = f"""
╔══════════════════════════════════════════════════════════════╗
║              CODE CHANGE REQUEST                             ║
╠══════════════════════════════════════════════════════════════╣
║ Task: {task_description[:50]}...
║ Branch: {branch_name}
╠══════════════════════════════════════════════════════════════╣
║
║ Target Files Modified: {len(modifications)} file(s)
"""
        for mod in modifications:
            output_report += f"║   ~ {mod.get('file', 'unknown')}\n"

        output_report += f"""║
║ Sandbox Test Results (VENV ISOLATED):
║   🧪 Smoke tests: {'✅ PASSED' if tests_passed else '❌ FAILED'}
╚══════════════════════════════════════════════════════════════╝

Test Output Preview:
{test_output[-200:]}
"""
        logger.info(f"[SelfModifier] Report ready:\n{output_report}")

        if not tests_passed:
            self.git.delete_branch(branch_name)
            self.sandbox.cleanup(branch_name)
            return f"Sandbox tests FAILED! Modification safely discarded.\n\n{output_report}"

        # 5. User Confirmation
        logger.info("[SelfModifier] 🔐 Requesting dual-channel approval...")
        approved = self.gate.request_approval(
            description=f"Code Modification: {task_description[:40]}",
            operation_type="code_modify"
        )

        if not approved:
            self.git.delete_branch(branch_name)
            self.sandbox.cleanup(branch_name)
            return "Modification DENIED by user. Branch deleted and sandbox discarded."

        # 6. Apply to Production
        logger.info("[SelfModifier] ✅ Approved. Applying to production...")
        
        # Apply the physical files (since git merge across detached sandbox is complex)
        # We write straight to D:\CRAVE, then commit on the feature branch, then merge.
        try:
            for mod in modifications:
                file_path = mod.get("file", "")
                content = mod.get("content", "")
                full_path = Path(CRAVE_ROOT) / file_path
                os.makedirs(full_path.parent, exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
            
            # Commit on feature branch
            self.git.checkpoint(f"Apply autonomous modification: {task_description}")
            
            # Merge to main
            merge_ok = self.git.merge_to_main(branch_name)
            
            if not merge_ok:
                return "Failed to merge feature branch to main. Production state may be inconsistent!"
                
            # Post-Merge Production Smoke Test
            logger.info("[SelfModifier] Running production smoke test...")
            if not self.git.auto_revert_if_broken(base_commit):
                return "Production smoke tests FAILED! Automatically rolled back to safe state."

            self.sandbox.cleanup(branch_name)
            
            # Log to reasoning
            try:
                from src.core.reasoning_log import get_reasoning_log
                get_reasoning_log().log_action(
                    action="CODE_SELF_MODIFICATION",
                    trigger=task_description,
                    reasoning={"branch": branch_name, "files": len(modifications)},
                    result="MERGED_SUCCESSFULLY"
                )
            except:
                pass

            return f"✅ Feature successfully implemented and verified in production!\n\n{output_report}"

        except Exception as e:
            logger.error(f"[SelfModifier] Fatal error during merge: {e}")
            self.git.rollback(base_commit)

            # Lock error class after 3 failed modifications
            try:
                from src.core.auto_heal_tracker import lock_error
                error_class = type(e).__name__
                lock_error(error_class, hours=24)
            except Exception:
                pass

            # Telegram alert on failure
            try:
                from Sub_Projects.Trading.telegram_interface import tg
                tg.send(
                    f"❌ <b>SELF-MODIFICATION FAILED</b>\n"
                    f"Task: {task_description[:80]}\n"
                    f"Error: {e}\n"
                    f"Action: Rolled back safely."
                )
            except Exception:
                pass

            return f"Fatal error. Rolled back safely. {e}"
