"""
CRAVE Phase 7 — Native Network Scanner
Provides local Python-based network reconnaissance, avoiding the need 
to boot the full Kali WSL instance for simple host discovery.
"""

import socket
import concurrent.futures
from typing import List, Dict, Optional

class PortScanner:
    def __init__(self, target_ip: str, timeout: float = 1.0):
        self.target_ip = target_ip
        self.timeout = timeout
        
    def scan_port(self, port: int) -> Optional[int]:
        """Attempt to connect to a specific port."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(self.timeout)
                if s.connect_ex((self.target_ip, port)) == 0:
                    return port
        except:
            pass
        return None

    def scan_top_ports(self) -> List[int]:
        """Scan the top 100 most common ports concurrently."""
        top_ports = [
            20, 21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445, 
            993, 995, 1723, 3306, 3389, 5900, 8080, 8443
        ]
        
        open_ports = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(self.scan_port, p) for p in top_ports]
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res:
                    open_ports.append(res)
                    
        return sorted(open_ports)

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    print(f"Scanning {target}...")
    scanner = PortScanner(target)
    ports = scanner.scan_top_ports()
    print(f"Open ports: {ports}")
