"""
CRAVE Phase 9 - Memory Bank (Trading Vault)
Logs the physical metadata, mathematical setup, and psychological rationale 
behind every single trade. Then evaluates the win/loss distribution on a rolling schedule
to objectively grade the StrategyAgent's algorithmic performance.
"""

import json
import os
import logging
from datetime import datetime
import numpy as np

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import LabelEncoder
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

logger = logging.getLogger("crave.core.memory_bank")

class MemoryBank:
    def __init__(self):
        # We store the memory physically in the encrypted Data directory
        self.memory_dir = os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "data")
        self.db_file = os.path.join(self.memory_dir, "trading_memory.json")
        self.task_db_file = os.path.join(self.memory_dir, "task_memory.json")
        self.knowledge_file = os.path.join(self.memory_dir, "knowledge_graph.json")
        self._ensure_db()
        
        # Fast in-memory knowledge cache (flushed to disk periodically)
        self._knowledge_cache = self._load_knowledge()
        
        self.ml_model = None
        self.label_encoders = {}
        if ML_AVAILABLE:
            self._train_ml_model()

    def _ensure_db(self):
        """Creates the JSON database structure if it doesn't exist."""
        if not os.path.exists(self.memory_dir):
            os.makedirs(self.memory_dir, exist_ok=True)
            
        if not os.path.exists(self.db_file):
            with open(self.db_file, "w", encoding="utf-8") as f:
                json.dump({"active_trades": {}, "closed_trades": []}, f, indent=4)
                
        if not os.path.exists(self.task_db_file):
            with open(self.task_db_file, "w", encoding="utf-8") as f:
                json.dump({"active_tasks": {}, "historical_tasks": []}, f, indent=4)

        if not os.path.exists(self.knowledge_file):
            with open(self.knowledge_file, "w", encoding="utf-8") as f:
                json.dump({"entities": {}, "decisions": []}, f, indent=2)

    def _load_knowledge(self) -> dict:
        """Load knowledge graph into memory for instant access."""
        try:
            with open(self.knowledge_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"entities": {}, "decisions": []}

    def _flush_knowledge(self):
        """Persist in-memory knowledge cache to disk."""
        try:
            with open(self.knowledge_file, "w", encoding="utf-8") as f:
                json.dump(self._knowledge_cache, f, indent=2)
        except Exception as e:
            logger.error(f"Knowledge flush failed: {e}")

    # ─── FAST KNOWLEDGE GRAPH (replaces MCP server-memory) ───────────────────

    def log_decision(self, category: str, detail: str):
        """Log a decision to the fast in-memory knowledge graph."""
        entry = {
            "category": category,
            "detail": detail,
            "timestamp": datetime.now().isoformat(),
        }
        self._knowledge_cache.setdefault("decisions", []).append(entry)
        # Flush every 10 decisions to avoid disk thrashing
        if len(self._knowledge_cache["decisions"]) % 10 == 0:
            self._flush_knowledge()

    def store_entity(self, name: str, entity_type: str, data: dict):
        """Store a named entity (person, concept, asset) in the knowledge graph."""
        self._knowledge_cache.setdefault("entities", {})[name] = {
            "type": entity_type,
            "data": data,
            "updated": datetime.now().isoformat(),
        }
        self._flush_knowledge()

    def recall(self, query: str) -> list:
        """Search the knowledge graph for matching decisions or entities."""
        results = []
        q = query.lower()
        # Search decisions
        for d in self._knowledge_cache.get("decisions", []):
            if q in d.get("category", "").lower() or q in d.get("detail", "").lower():
                results.append(d)
        # Search entities
        for name, ent in self._knowledge_cache.get("entities", {}).items():
            if q in name.lower() or q in str(ent.get("data", "")).lower():
                results.append({"entity": name, **ent})
        return results[-20:]  # Return max 20 most recent matches

    def _load(self, db_path) -> dict:
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read MemoryBank at {db_path}: {e}")
            return {}

    def _save(self, data: dict, db_path: str):
        try:
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to write MemoryBank at {db_path}: {e}")

    # ─── GLOBAL ML TASK LOOP ─────────────────────────────────────────────────

    def log_task_start(self, task_id: str, task_type: str, parameters: dict):
        """Log the start of any system task (research, email, execution, etc)."""
        db = self._load(self.task_db_file)
        if "active_tasks" not in db: db["active_tasks"] = {}
        
        # Simplify parameters for ML feature extraction
        feature_count = len(parameters.keys())
        is_complex = 1 if feature_count > 3 else 0
        hour_of_day = datetime.now().hour
        
        db["active_tasks"][task_id] = {
            "task_type": task_type,
            "hour_of_day": hour_of_day,
            "feature_count": feature_count,
            "is_complex": is_complex,
            "start_time": datetime.now().isoformat()
        }
        self._save(db, self.task_db_file)
        
    def log_task_end(self, task_id: str, success: bool, error_msg: str = ""):
        """Log the resolution of a task to train the ML loop."""
        db = self._load(self.task_db_file)
        task = db.get("active_tasks", {}).pop(task_id, None)
        
        if not task: return
        
        task["success"] = 1 if success else 0
        task["error"] = error_msg
        task["end_time"] = datetime.now().isoformat()
        
        if "historical_tasks" not in db: db["historical_tasks"] = []
        db["historical_tasks"].append(task)
        self._save(db, self.task_db_file)
        
        # Retrain every 10 new tasks
        if ML_AVAILABLE and len(db["historical_tasks"]) % 10 == 0:
            self._train_ml_model()

    def _train_ml_model(self):
        """Trains a local Random Forest Regressor/Classifier on user tasks."""
        db = self._load(self.task_db_file)
        history = db.get("historical_tasks", [])
        
        # Need at least 20 samples to start predicting accurately
        if len(history) < 20:
            return
            
        X = []
        y = []
        
        # We need to encode categorical 'task_type'
        self.label_encoders['task_type'] = LabelEncoder()
        types = [t["task_type"] for t in history]
        self.label_encoders['task_type'].fit(types)
        
        for t in history:
            encoded_type = self.label_encoders['task_type'].transform([t["task_type"]])[0]
            X.append([encoded_type, t.get("hour_of_day", 12), t.get("feature_count", 1), t.get("is_complex", 0)])
            y.append(t.get("success", 0))
            
        self.ml_model = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
        self.ml_model.fit(X, y)
        logger.info(f"MemoryBank ML Model retrained on {len(history)} historical data points.")

    def predict_success_probability(self, task_type: str, parameters: dict) -> float:
        """
        Queries the SCi-Kit ML Engine: "Based on my history, what is the % chance this task succeeds?"
        """
        if not ML_AVAILABLE or self.ml_model is None:
            return 0.85 # Optimistic default if no model
            
        try:
            feature_count = len(parameters.keys())
            is_complex = 1 if feature_count > 3 else 0
            hour_of_day = datetime.now().hour
            
            # Handle unseen task types
            if task_type in self.label_encoders['task_type'].classes_:
                encoded_type = self.label_encoders['task_type'].transform([task_type])[0]
            else:
                encoded_type = -1 # Unknown
                
            features = np.array([[encoded_type, hour_of_day, feature_count, is_complex]])
            prob = self.ml_model.predict_proba(features)[0]
            
            # predict_proba returns [prob_fail, prob_success]
            success_prob = prob[1] if len(prob) > 1 else prob[0]
            return round(success_prob, 2)
        except Exception as e:
            logger.warning(f"ML Prediction failed: {e}")
            return 0.85

    # ─── TRADING SPECIFIC (LEGACY) ───────────────────────────────────────────

    def log_trade_entry(self, trade_id: str, symbol: str, direction: str, entry_price: float, lot_size: float, smc_context: dict):
        db = self._load(self.db_file)
        db["active_trades"][trade_id] = {
            "symbol": symbol,
            "direction": direction,
            "entry_time": datetime.now().isoformat(),
            "entry_price": entry_price,
            "lot_size": lot_size,
            "rationale": smc_context,
            "predicted_result": "win"
        }
        self._save(db, self.db_file)
        logger.info(f"Trade {trade_id} etched into memory logs.")

    def log_trade_exit(self, trade_id: str, exit_price: float, pnl_dollars: float):
        db = self._load(self.db_file)
        trade = db["active_trades"].pop(trade_id, None)
        
        if not trade:
            return

        trade["exit_time"] = datetime.now().isoformat()
        trade["exit_price"] = exit_price
        trade["pnl_dollars"] = pnl_dollars
        trade["actual_result"] = "win" if pnl_dollars > 0 else "loss" if pnl_dollars < 0 else "breakeven"
        
        db["closed_trades"].append(trade)
        self._save(db, self.db_file)
        
        # Also log trading as a generic ML task success/failure!
        self.log_task_start(f"trade_{trade_id}", "market_execution", {"symbol": trade["symbol"]})
        self.log_task_end(f"trade_{trade_id}", success=(trade["actual_result"] == "win"))

    def analyze_consistency(self, N: int = 50) -> dict:
        db = self._load(self.db_file)
        history = list(db.get("closed_trades", []))
        
        if len(history) < 10:
            return {"status": "warming_up", "message": f"Only {len(history)} trades closed. Need 10 minimum."}
            
        recent = history[-N:]
        wins = sum(1 for t in recent if t["actual_result"] == "win")
        total = len(recent)
        
        if total == 0: return {"status": "neutral"}
        
        win_rate = (wins / total) * 100
        gross_pnl = sum(t.get("pnl_dollars", 0) for t in recent)
        
        verdict = "healthy"
        if win_rate < 45.0: verdict = "broken"
        elif win_rate > 60.0: verdict = "highly_optimal"
            
        return {
            "status": verdict,
            "sample_size": total,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(gross_pnl, 2)
        }
