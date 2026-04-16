"""
CRAVE Phase 7 - N8N Webhook Automation Agent
Triggers complex workflow graphs running on a standalone n8n instance
to execute advanced multi-app logic (Instagram posting, email blasts).
"""

import requests
import logging

logger = logging.getLogger("crave.agents.n8n")

class N8NAgent:
    def __init__(self):
        # By default, n8n runs locally on port 5678
        self.base_url = "http://localhost:5678/webhook/"
        
    def trigger_workflow(self, webhook_id: str, payload_data: dict) -> str:
        """
        Fires a stateless webhook to the n8n backend passing JSON values.
        Example: trigger_workflow("social-post", {"platform": "x", "content": "Hello Worlds"})
        """
        try:
            url = f"{self.base_url}{webhook_id}"
            logger.info(f"Firing n8n workflow trigger to {url}")
            
            # For Test webhooks, use /webhook-test/{id}
            response = requests.post(url, json=payload_data, timeout=10)
            
            # n8n typically returns a success status if the node executed
            if response.status_code == 200:
                ret = response.json()
                return f"SUCCESS: n8n workflow {webhook_id} fired. Response: {ret.get('message', 'OK')}"
            else:
                return f"n8n Workflow Refused (Code {response.status_code}): {response.text}"
                
        except requests.exceptions.ConnectionError:
            return "ERROR: n8n local instance unreachable. Ensure n8n is running on localhost:5678."
        except Exception as e:
            return f"CRITICAL n8n webhook error: {e}"
