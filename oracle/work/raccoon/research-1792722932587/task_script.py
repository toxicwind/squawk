import os
import json

# Define paths
workspace_dir = "/home/toxic"
estate_dir = "/home/toxic/pens/Pens"
config_path = os.path.join(workspace_dir, "delendai.config.json")
estate_config_path = os.path.join(estate_dir, "delendai.config.json")
agents_md_path = os.path.join(estate_dir, "AGENTS.md")
experimental_bin_path = os.path.join(estate_dir, "bin", "delend-experimental")

# Check if files exist
files_to_check = [config_path, estate_config_path, agents_md_path, experimental_bin_path]
existing_files = {}

for f in files_to_check:
    if os.path.exists(f):
        with open(f, 'r') as file:
            existing_files[f] = file.read()
    else:
        print(f"File not found: {f}")

# Print contents for analysis
for path, content in existing_files.items():
    print(f"--- {path} ---")
    print(content)
    print("-" * 20)
