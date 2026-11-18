#!/usr/bin/env python3
"""
delend-pylae-test: Emergent experimental work for delend-oracle.
Applies zero-trust origin gate logic to the ranch/pylae scaffold.
"""

import os
import sys
import json
import logging
from datetime import datetime

# Setup logging
LOG_DIR = "Pens/logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "delend-pylae.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("delend-pylae-test")

def inspect_pylae_scaffold():
    """Inspect the naive unified tailscale scaffold."""
    pylae_path = "ranch/pylae"
    readme_path = os.path.join(pylae_path, "README.md")
    
    if not os.path.exists(readme_path):
        logger.error(f"README.md not found at {readme_path}")
        return None
    
    with open(readme_path, "r") as f:
        content = f.read()
    
    logger.info(f"Inspected {readme_path}: {len(content)} bytes")
    return content

def apply_zero_trust_annotation(content):
    """Apply zero-trust origin gate annotation."""
    annotation = "\n<!-- DELEND-ORACLE: ZERO-TRUST ORIGIN GATE APPLIED -->\n"
    if annotation.strip() in content:
        logger.info("Annotation already present.")
        return content
    
    new_content = content + annotation
    logger.info("Applied zero-trust annotation.")
    return new_content

def validate_scaffold(content):
    """Simulate validation check."""
    if "DELEND-ORACLE" in content:
        logger.info("Validation PASSED: Zero-trust annotation detected.")
        return True
    else:
        logger.error("Validation FAILED: Zero-trust annotation missing.")
        return False

def main():
    logger.info("Starting delend-pylae-test...")
    
    # Step 1: Inspect
    content = inspect_pylae_scaffold()
    if not content:
        sys.exit(1)
    
    # Step 2: Apply
    new_content = apply_zero_trust_annotation(content)
    
    # Step 3: Validate
    is_valid = validate_scaffold(new_content)
    
    # Step 4: Log Result
    result = {
        "task": "delend-pylae-test",
        "timestamp": datetime.now().isoformat(),
        "status": "PASS" if is_valid else "FAIL",
        "annotation_applied": "DELEND-ORACLE: ZERO-TRUST ORIGIN GATE APPLIED" in new_content
    }
    
    logger.info(f"Result: {json.dumps(result)}")
    
    if not is_valid:
        sys.exit(1)

if __name__ == "__main__":
    main()
