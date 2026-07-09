import sys
import os

# Ensure Chroma can use a modern sqlite3 on Python 3.8 systems
if sys.version_info < (3, 9):
    try:
        import pysqlite3
        sys.modules["sqlite3"] = pysqlite3
    except ImportError:
        pass

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import json
import subprocess
import uuid
import tempfile
import threading
import time
import shutil
import re
import signal
import argparse
from pathlib import Path
from datetime import datetime

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Backend server for WriteHERE application')
parser.add_argument('--port', type=int, default=5001, help='Port to run the server on')
args = parser.parse_args()

app = Flask(__name__)
# Enable CORS with more specific options
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
# Initialize Socket.IO with broader CORS settings for development
socketio = SocketIO(app, 
                    cors_allowed_origins="*", 
                    async_mode='threading',
                    logger=False, # disable logger
                    engineio_logger=False)

# Storage for task status and results
task_storage = {}
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

def _load_result_or_error(output_file, stderr_text=""):
    """Load a one-line JSONL task result and preserve useful engine errors."""
    if not os.path.exists(output_file):
        return None, "Output file not generated"

    with open(output_file, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    if not content:
        tail = stderr_text.strip()[-4000:]
        detail = "Output file generated but empty"
        if tail:
            detail += "\n\nEngine stderr tail:\n" + tail
        return None, detail

    try:
        result_data = json.loads(content.splitlines()[0])
        return result_data.get("result", "No result available"), None
    except Exception as exc:
        tail = stderr_text.strip()[-4000:]
        detail = f"Failed to parse output file: {exc}"
        if tail:
            detail += "\n\nEngine stderr tail:\n" + tail
        return None, detail

def reload_task_storage():
    """Reload task storage from the file system"""
    global task_storage
    
    # Iterate through all folders in the results directory
    for task_id in os.listdir(RESULTS_DIR):
        task_dir = os.path.join(RESULTS_DIR, task_id)
        if not os.path.isdir(task_dir):
            continue
            
        # Check if this is a completed task with results
        result_file = os.path.join(task_dir, 'result.jsonl')
        done_file = os.path.join(task_dir, 'done.txt')
        
        if os.path.exists(result_file):
            # Add task to storage if not already there
            if task_id not in task_storage:
                creation_time = os.path.getctime(task_dir)
                task_storage[task_id] = {
                    "status": "completed" if os.path.exists(done_file) else "running",
                    "start_time": creation_time
                }
                
                # Try to extract model information from run.sh
                run_sh_file = os.path.join(task_dir, 'run.sh')
                if os.path.exists(run_sh_file):
                    try:
                        with open(run_sh_file, 'r') as f:
                            run_script = f.read()
                            # Extract model name from command line arguments
                            model_match = run_script.split("--model ")[1].split(" ")[0] if "--model " in run_script else None
                            if model_match:
                                task_storage[task_id]["model"] = model_match
                            
                            # Check if it's a report with search
                            if "--engine-backend " in run_script:
                                engine_backend = run_script.split("--engine-backend ")[1].split(" ")[0]
                                if engine_backend != "none":
                                    task_storage[task_id]["search_engine"] = engine_backend
                    except Exception as e:
                        print(f"Error extracting model info from run.sh for {task_id}: {str(e)}")
                
                # Load result if available
                try:
                    with open(result_file, 'r') as f:
                        result_data = json.load(f)
                        task_storage[task_id]["result"] = result_data.get("result", "No result available")
                except Exception as e:
                    print(f"Error loading result file for {task_id}: {str(e)}")
                    task_storage[task_id]["error"] = f"Failed to load output file: {str(e)}"

# Load existing tasks on startup
reload_task_storage()

def run_story_generation(task_id, prompt, model, api_keys):
    """
    Run the story generation script as a subprocess
    """
    task_dir = os.path.join(RESULTS_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    
    # Create a records directory for nodes.json
    records_dir = os.path.join(task_dir, 'records')
    os.makedirs(records_dir, exist_ok=True)
    
    # Create a temporary input file with the prompt
    input_file = os.path.join(task_dir, 'input.jsonl')
    with open(input_file, 'w') as f:
        json.dump({
            "id": task_id,
            "field": "inputs",
            "value": prompt,
            "ori": {"example_id": task_id, "inputs": prompt, "subset": "user"}
        }, f)
        f.write('\n')
    
    output_file = os.path.join(task_dir, 'result.jsonl')
    done_file = os.path.join(task_dir, 'done.txt')
    nodes_file = os.path.join(records_dir, 'nodes.json')
    
    # Create environment file with API keys
    env_file = os.path.join(task_dir, 'api_key.env')
    with open(env_file, 'w') as f:
        if 'openai' in api_keys and api_keys['openai']:
            f.write(f"OPENAI={api_keys['openai']}\n")
        if 'claude' in api_keys and api_keys['claude']:
            f.write(f"CLAUDE={api_keys['claude']}\n")
        if 'gemini' in api_keys and api_keys['gemini']:
            f.write(f"GEMINI={api_keys['gemini']}\n")
        if 'deepseek' in api_keys and api_keys['deepseek']:
            f.write(f"DEEPSEEK={api_keys['deepseek']}\n")
        if 'serpapi' in api_keys and api_keys['serpapi']:
            f.write(f"SERPAPI={api_keys['serpapi']}\n")
        if 'nebulacoder' in api_keys and api_keys['nebulacoder']:
            f.write(f"NEBULACODER={api_keys['nebulacoder']}\n")
    
    # Create a script to run the engine with the appropriate environment
    script_path = os.path.join(task_dir, 'run.sh')
    recursive_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../recursive'))
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    with open(script_path, 'w') as f:
        f.write(f"""#!/bin/bash
cd "{recursive_dir}"

# Load API keys from env file and export them
set -a
source "{env_file}"
set +a

export TASK_ENV_FILE="{env_file}"
export PYTHONPATH="{project_root}:$PYTHONPATH"

{sys.executable} engine.py --filename "{input_file}" --output-filename "{output_file}" --done-flag-file "{done_file}" --model {model} --mode story --nodes-json-file "{nodes_file}"
""")
    
    os.chmod(script_path, 0o755)
    
    # Update task status to "running"
    task_storage[task_id] = {
        "status": "running", 
        "start_time": time.time(),
        "model": model
    }
    
    # Start task progress monitoring in a background thread
    monitoring_thread = threading.Thread(
        target=monitor_task_progress,
        args=(task_id, records_dir)
    )
    monitoring_thread.daemon = True
    monitoring_thread.start()
    
    try:
        # Run the script
        process = subprocess.Popen(['/bin/bash', script_path], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
        # Store the process object in task_storage for later termination
        task_storage[task_id]["process"] = process
        stdout, stderr = process.communicate()
        
        # Check if the process completed successfully
        if process.returncode == 0:
            result, error = _load_result_or_error(
                output_file, stderr.decode('utf-8', errors='replace'))
            if error:
                task_storage[task_id]["status"] = "error"
                task_storage[task_id]["error"] = error
            else:
                task_storage[task_id]["status"] = "completed"
                task_storage[task_id]["result"] = result
        else:
            task_storage[task_id]["status"] = "error"
            task_storage[task_id]["error"] = stderr.decode('utf-8', errors='replace')
    except Exception as e:
        task_storage[task_id]["status"] = "error"
        task_storage[task_id]["error"] = str(e)

def run_report_generation(task_id, prompt, model, enable_search, search_engine, api_keys,
                          use_knowledge_base=False, knowledge_base_name=None):
    """
    Run the report generation script as a subprocess
    """
    task_dir = os.path.join(RESULTS_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    
    # Create a records directory for nodes.json
    records_dir = os.path.join(task_dir, 'records')
    os.makedirs(records_dir, exist_ok=True)
    
    # Create a temporary input file with the prompt
    input_file = os.path.join(task_dir, 'input.jsonl')
    with open(input_file, 'w') as f:
        json.dump({
            "topic": "",
            "intent": "",
            "domain": "",
            "id": task_id,
            "prompt": prompt
        }, f)
        f.write('\n')
    
    output_file = os.path.join(task_dir, 'result.jsonl')
    done_file = os.path.join(task_dir, 'done.txt')
    nodes_file = os.path.join(records_dir, 'nodes.json')
    
    # Create environment file with API keys
    env_file = os.path.join(task_dir, 'api_key.env')
    with open(env_file, 'w') as f:
        if 'openai' in api_keys and api_keys['openai']:
            f.write(f"OPENAI={api_keys['openai']}\n")
        if 'claude' in api_keys and api_keys['claude']:
            f.write(f"CLAUDE={api_keys['claude']}\n")
        if 'gemini' in api_keys and api_keys['gemini']:
            f.write(f"GEMINI={api_keys['gemini']}\n")
        if 'deepseek' in api_keys and api_keys['deepseek']:
            f.write(f"DEEPSEEK={api_keys['deepseek']}\n")
        if 'serpapi' in api_keys and api_keys['serpapi']:
            f.write(f"SERPAPI={api_keys['serpapi']}\n")
        if 'nebulacoder' in api_keys and api_keys['nebulacoder']:
            f.write(f"NEBULACODER={api_keys['nebulacoder']}\n")
    
    # Create a script to run the engine with the appropriate environment
    script_path = os.path.join(task_dir, 'run.sh')
    # Hybrid mode: when both KB and web search are enabled, keep the search
    # engine backend so the orchestrator can do KB-first then fall back to web.
    if use_knowledge_base and knowledge_base_name:
        if enable_search and search_engine:
            engine_backend = search_engine
        else:
            engine_backend = "kb"
    else:
        engine_backend = search_engine if enable_search else "none"
    recursive_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../recursive'))
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    # Optional shim to ensure engine subprocess can use pysqlite3 for Chroma
    kb_exports = ""
    pythonpath_shim = ""
    if use_knowledge_base and knowledge_base_name:
        kb_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'knowledge_bases'))
        shim_dir = os.path.join(task_dir, 'pysqlite3_shim')
        os.makedirs(shim_dir, exist_ok=True)
        sitecustomize_file = os.path.join(shim_dir, 'sitecustomize.py')
        with open(sitecustomize_file, 'w') as sf:
            sf.write("""import sys\ntry:\n    import pysqlite3\n    sys.modules['sqlite3'] = pysqlite3\nexcept ImportError:\n    pass\n""")

        # Support external Chroma databases configured via environment variables
        normalized_name = knowledge_base_name.strip().upper()
        external_path_env = f"WRITEHERE_KB_{normalized_name}_PATH"
        external_embedding_env = f"WRITEHERE_KB_{normalized_name}_EMBEDDING"
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        external_path = os.environ.get(external_path_env) or os.path.join(project_root, 'testdata', 'chroma_data')
        external_embedding = os.environ.get(external_embedding_env, "")

        if knowledge_base_name.lower() == "testdata" and os.path.isdir(external_path):
            kb_exports = f"""
export WRITEHERE_USE_KB="true"
export WRITEHERE_KB_NAME="{knowledge_base_name}"
export WRITEHERE_KB_PATH="{kb_base_path}"
export {external_path_env}="{external_path}"
export {external_embedding_env}="{external_embedding or TESTDATA_EMBEDDING_MODEL}"
export PYTHONPATH="{shim_dir}:$PYTHONPATH"
"""
        elif knowledge_base_name.lower() == "large_kb":
            large_kb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge_bases', 'large_kb', 'chroma_data')
            kb_exports = f"""
export WRITEHERE_USE_KB="true"
export WRITEHERE_KB_NAME="{knowledge_base_name}"
export WRITEHERE_KB_PATH="{kb_base_path}"
export {external_path_env}="{large_kb_path}"
export {external_embedding_env}="{external_embedding or LARGE_KB_EMBEDDING_MODEL}"
export PYTHONPATH="{shim_dir}:$PYTHONPATH"
"""
        else:
            kb_exports = f"""
export WRITEHERE_USE_KB="true"
export WRITEHERE_KB_NAME="{knowledge_base_name}"
export WRITEHERE_KB_PATH="{kb_base_path}"
export PYTHONPATH="{shim_dir}:$PYTHONPATH"
"""
    with open(script_path, 'w') as f:
        f.write(f"""#!/bin/bash
cd "{recursive_dir}"

# Load API keys from env file and export them
set -a
source "{env_file}"
set +a

export TASK_ENV_FILE="{env_file}"{kb_exports}
export PYTHONPATH="{project_root}:$PYTHONPATH"

{sys.executable} engine.py --filename "{input_file}" --output-filename "{output_file}" --done-flag-file "{done_file}" --model {model} --engine-backend {engine_backend} --mode report --nodes-json-file "{nodes_file}"
""")
    
    os.chmod(script_path, 0o755)
    
    # Update task status to "running"
    task_storage[task_id] = {
        "status": "running", 
        "start_time": time.time(),
        "model": model,
        "search_engine": engine_backend if enable_search else None
    }
    
    # Start task progress monitoring in a background thread
    monitoring_thread = threading.Thread(
        target=monitor_task_progress,
        args=(task_id, records_dir)
    )
    monitoring_thread.daemon = True
    monitoring_thread.start()
    
    try:
        # Run the script
        process = subprocess.Popen(['/bin/bash', script_path], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
        # Store the process object in task_storage for later termination
        task_storage[task_id]["process"] = process
        stdout, stderr = process.communicate()
        
        # Check if the process completed successfully
        if process.returncode == 0:
            result, error = _load_result_or_error(
                output_file, stderr.decode('utf-8', errors='replace'))
            if error:
                task_storage[task_id]["status"] = "error"
                task_storage[task_id]["error"] = error
            else:
                task_storage[task_id]["status"] = "completed"
                task_storage[task_id]["result"] = result
        else:
            task_storage[task_id]["status"] = "error"
            task_storage[task_id]["error"] = stderr.decode('utf-8', errors='replace')
    except Exception as e:
        task_storage[task_id]["status"] = "error"
        task_storage[task_id]["error"] = str(e)

@app.route('/api/generate-story', methods=['POST'])
def api_generate_story():
    data = request.json
    
    # Validate request
    required_fields = ['prompt', 'model', 'apiKeys']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    # Generate a unique task ID
    task_id = f"story-{uuid.uuid4()}"
    
    # Start the generation in a background thread
    thread = threading.Thread(
        target=run_story_generation,
        args=(task_id, data['prompt'], data['model'], data['apiKeys'])
    )
    thread.start()
    
    return jsonify({
        "taskId": task_id,
        "status": "started"
    })

@app.route('/api/generate-report', methods=['POST'])
def api_generate_report():
    data = request.json
    
    # Validate request
    required_fields = ['prompt', 'model', 'apiKeys']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    # Set defaults
    enable_search = data.get('enableSearch', True)
    search_engine = data.get('searchEngine', 'bing')  # Default to Bing since it doesn't require API key
    use_knowledge_base = data.get('useKnowledgeBase', False)
    knowledge_base_name = data.get('knowledgeBaseName', None)

    if use_knowledge_base and (not knowledge_base_name or not isinstance(knowledge_base_name, str)):
        return jsonify({"error": "knowledgeBaseName is required when useKnowledgeBase is true"}), 400

    # Generate a unique task ID
    task_id = f"report-{uuid.uuid4()}"

    # Start the generation in a background thread
    thread = threading.Thread(
        target=run_report_generation,
        args=(task_id, data['prompt'], data['model'], enable_search, search_engine, data['apiKeys'],
              use_knowledge_base, knowledge_base_name)
    )
    thread.start()
    
    return jsonify({
        "taskId": task_id,
        "status": "started"
    })

@app.route('/api/status/<task_id>', methods=['GET'])
def api_get_status(task_id):
    # If task is not in memory, try to load it
    if task_id not in task_storage:
        task_dir = os.path.join(RESULTS_DIR, task_id)
        print('debug')
        if os.path.isdir(task_dir):
            # Load task into memory
            result_file = os.path.join(task_dir, 'result.jsonl')
            done_file = os.path.join(task_dir, 'done.txt')
            
            if os.path.exists(result_file):
                creation_time = os.path.getctime(task_dir)
                task_storage[task_id] = {
                    "status": "completed" if os.path.exists(done_file) else "running",
                    "start_time": creation_time
                }
                
                # Load result if available
                try:
                    with open(result_file, 'r') as f:
                        result_data = json.load(f)
                        task_storage[task_id]["result"] = result_data.get("result", "No result available")
                except Exception as e:
                    print(f"Error loading result file for {task_id}: {str(e)}")
                    task_storage[task_id]["error"] = f"Failed to load output file: {str(e)}"
            else:
                return jsonify({"error": "Task not found or incomplete"}), 404
        else:
            return jsonify({"error": "Task not found"}), 404
    
    task = task_storage[task_id]
    
    # Check if we need to update status from the done file
    task_dir = os.path.join(RESULTS_DIR, task_id)
    done_file = os.path.join(task_dir, 'done.txt')
    
    if task["status"] == "running" and os.path.exists(done_file):
        task["status"] = "completed"
    
    return jsonify({
        "taskId": task_id,
        "status": task["status"],
        "error": task.get("error"),
        "elapsedTime": time.time() - task["start_time"],
        "model": task.get("model", "unknown"),
        "searchEngine": task.get("search_engine")
    })

@app.route('/api/result/<task_id>', methods=['GET'])
def api_get_result(task_id):
    # If task is not in memory, try to load it
    if task_id not in task_storage:
        task_dir = os.path.join(RESULTS_DIR, task_id)
        if os.path.isdir(task_dir):
            # Load task into memory
            result_file = os.path.join(task_dir, 'result.jsonl')
            done_file = os.path.join(task_dir, 'done.txt')
            
            if os.path.exists(result_file):
                creation_time = os.path.getctime(task_dir)
                task_storage[task_id] = {
                    "status": "completed" if os.path.exists(done_file) else "running",
                    "start_time": creation_time
                }
                
                # Load result if available
                try:
                    with open(result_file, 'r') as f:
                        result_data = json.load(f)
                        task_storage[task_id]["result"] = result_data.get("result", "No result available")
                except Exception as e:
                    print(f"Error loading result file for {task_id}: {str(e)}")
                    task_storage[task_id]["error"] = f"Failed to load output file: {str(e)}"
                    return jsonify({"error": f"Failed to load output file: {str(e)}"}), 500
            else:
                return jsonify({"error": "Task result file not found"}), 404
        else:
            return jsonify({"error": "Task not found"}), 404
    
    result_md_dir = os.path.join(RESULTS_DIR, 'records', task_id, 'report.md')
    task = task_storage[task_id]
    
    # We'll allow getting results even if status is not completed as long as we have the result data
    if "result" not in task:
        # Check if the result.md file exists
        if not os.path.exists(result_md_dir):
            return jsonify({"error": "Task result not available"}), 400
        else:
            with open(result_md_dir, 'r') as f:
                task["result"] = f.read()
        # Check if the result.md file exists
        if not os.path.exists(result_md_dir):
            return jsonify({"error": "Task result not available"}), 400
        else:
            with open(result_md_dir, 'r') as f:
                task["result"] = f.read()
    
    return jsonify({
        "taskId": task_id,
        "result": task.get("result", "No result available"),
        "model": task.get("model", "unknown"),
        "searchEngine": task.get("search_engine")
    })


def transform_node_to_graph(node, seen_nodes=None, root=False):
    """
    Transform a node from the internal format to the format expected by the frontend
    Based on the display logic in display.py
    """
    if seen_nodes is None:
        seen_nodes = set()
        
    # Get the base node data
    task_info = node.get("task_info", {})
    
    # Use nid for the ID field
    node_id = node.get("nid", "")
    
    # Skip if we've seen this node before (prevents duplication)
    if node_id in seen_nodes and not root:
        return None
    
    # Add this node to the set of seen nodes
    seen_nodes.add(node_id)
    
    # Get the node status
    status = node.get("status", "UNKNOWN")
    
    # Determine if this is an execute node
    is_execute_node = node.get("node_type") == "EXECUTE_NODE"
    
    transformed = {
        "id": node_id,
        "goal": task_info.get("goal", "Unknown"),
        "task_type": task_info.get("task_type", "unknown"),
        "status": status,
        "dependency": task_info.get("dependency", []),
        "sub_tasks": [],
        "node_type": node.get("node_type", "UNKNOWN"),
        "is_execute_node": is_execute_node,
    }
    
    # Add action information if available
    if "result" in node:
        # The node.result dictionary contains actions as keys
        # Include both the latest action and all actions
        actions = []
        latest_action_name = None
        latest_action_result = None
        
        for action_name, action_data in node.get("result", {}).items():
            raw_result = action_data.get("result", {})
            action_result = raw_result.get("result", "") if isinstance(raw_result, dict) else raw_result
            action_time = action_data.get("time", "")
            
            actions.append({
                "name": action_name,
                "result": action_result,
                "time": action_time
            })
            
            # Track the latest action by time
            if not latest_action_name or action_time > node.get("result", {}).get(latest_action_name, {}).get("time", ""):
                latest_action_name = action_name
                latest_action_result = action_result
                
        if actions:
            transformed["actions"] = actions
        
        if latest_action_name:
            transformed["latest_action"] = {
                "name": latest_action_name,
                "result": latest_action_result
            }
    
    # For task graph visualization, we need to collect and flatten all subtasks
    # from the node hierarchy
    def collect_subtasks(current_node, parent_transformed):
        """Recursively collect all subtasks from a node and its children"""
        if not current_node:
            return
            
        # Get the inner graph of the current node
        inner = current_node.get("inner_graph", {})
        if not inner or "topological_task_queue" not in inner:
            return
            
        # Get and sort tasks by ID
        tasks = inner.get("topological_task_queue", [])
        sorted_tasks = sorted(
            tasks,
            key=lambda x: int(str(x.get("nid", "0")).split(".")[-1])
        )
        
        # Process each task
        for task in sorted_tasks:
            task_id = task.get("nid", "")
            
            # Skip duplicate nodes
            if task_id in seen_nodes and task_id != current_node.get("nid"):
                continue
                
            # Mark this node as seen
            seen_nodes.add(task_id)
            
            # Create the transformed task
            task_info = task.get("task_info", {})
            is_execute = task.get("node_type") == "EXECUTE_NODE"
            
            sub_task = {
                "id": task_id,
                "goal": task_info.get("goal", "Unknown"),
                "task_type": task_info.get("task_type", "unknown"),
                "status": task.get("status", "UNKNOWN"),
                "dependency": task_info.get("dependency", []),
                "sub_tasks": [],
                "node_type": task.get("node_type", "UNKNOWN"),
                "is_execute_node": is_execute
            }
            
            # Add action information if available
            if "result" in task:
                # The task.result dictionary contains actions as keys
                # Include both the latest action and all actions
                actions = []
                latest_action_name = None
                latest_action_result = None
                
                for action_name, action_data in task.get("result", {}).items():
                    raw_result = action_data.get("result", {})
                    action_result = raw_result.get("result", "") if isinstance(raw_result, dict) else raw_result
                    
                    actions.append({
                        "name": action_name,
                        "result": action_result,
                        "time": action_time
                    })
                    
                    # Track the latest action by time
                    if not latest_action_name or action_time > task.get("result", {}).get(latest_action_name, {}).get("time", ""):
                        latest_action_name = action_name
                        latest_action_result = action_result
                        
                if actions:
                    sub_task["actions"] = actions
                
                if latest_action_name:
                    sub_task["latest_action"] = {
                        "name": latest_action_name,
                        "result": latest_action_result
                    }
            
            # Add to parent's subtasks
            parent_transformed["sub_tasks"].append(sub_task)
            
            # For task graph visualization, we don't skip execute nodes
            # Instead we process their subtasks but mark them specially
            collect_subtasks(task, sub_task)
    
    # Start collecting subtasks from this node
    collect_subtasks(node, transformed)
    
    return transformed

@app.route('/api/task-graph/<task_id>', methods=['GET'])
def api_get_task_graph(task_id):
    """
    Get the task graph data (nodes and edges) for a specific task
    """
    # Check if the task directory exists
    task_dir = os.path.join(RESULTS_DIR, task_id)
    if not os.path.isdir(task_dir):
        return jsonify({"error": "Task not found"}), 404
    
    # Possible locations for the nodes.json file
    nodes_paths = [
        os.path.join(task_dir, 'records', 'nodes.json'),
        os.path.join(RESULTS_DIR, 'records', task_id, 'nodes.json')
    ]
    
    nodes_file = None
    for path in nodes_paths:
        if os.path.exists(path):
            nodes_file = path
            break
    
    if not nodes_file:
        # Create a simple task graph if we can't find the real one
        
        # Get prompt from input file
        input_file = os.path.join(task_dir, 'input.jsonl')
        prompt = "Unknown task"
        if os.path.exists(input_file):
            try:
                with open(input_file, 'r') as f:
                    input_data = json.load(f)
                    if 'value' in input_data:
                        prompt = input_data.get('value', '')
            except Exception as e:
                print(f"Error reading input file: {str(e)}")
        
        simple_graph = {
            "id": "",
            "goal": prompt,
            "task_type": "write",
            "status": "FINISH",
            "sub_tasks": [
                {
                    "id": "0",
                    "goal": "Task graph data not available",
                    "task_type": "think",
                    "status": "FINISH",
                    "sub_tasks": []
                }
            ]
        }
        
        return jsonify({
            "taskId": task_id,
            "taskGraph": simple_graph
        })
    
    try:
        with open(nodes_file, 'r') as f:
            nodes_data = json.load(f)
        
        # Transform the data to the format expected by the frontend
        transformed_graph = transform_node_to_graph(nodes_data, root=True)
        
        return jsonify({
            "taskId": task_id,
            "taskGraph": transformed_graph
        })
    except Exception as e:
        print(f"Error processing nodes.json: {str(e)}")
        return jsonify({"error": f"Failed to read task graph data: {str(e)}"}), 500

@app.route('/api/reload', methods=['POST'])
def api_reload_tasks():
    """Reload all tasks from the file system"""
    reload_task_storage()
    return jsonify({
        "status": "ok",
        "message": "Task storage reloaded",
        "taskCount": len(task_storage)
    })
    
@app.route('/api/stop-task/<task_id>', methods=['POST'])
def api_stop_task(task_id):
    """Stop a running task"""
    try:
        # Sanitize task_id to prevent path traversal
        if not re.match(r'^[a-zA-Z0-9_\-]+$', task_id):
            return jsonify({"status": "error", "error": "Invalid task ID format"}), 400
            
        # Check if task exists
        if task_id not in task_storage:
            return jsonify({"status": "error", "error": "Task not found"}), 404
            
        # Check if task is already completed or stopped
        if task_storage[task_id]["status"] in ["completed", "error", "stopped"]:
            return jsonify({
                "status": "ok",
                "message": f"Task {task_id} is already {task_storage[task_id]['status']}"
            })
        
          
        # Direct approach: Find the pid for the python engine.py process and kill it
        task_dir = os.path.join(RESULTS_DIR, task_id)

        # 1. Create a stop.txt file for the task to detect gracefully                                                 │ │
        stop_file = os.path.join(task_dir, 'stop.txt') 
        
        # First try to find the PID using ps command
        try:
            # For the specific task_id, find the python engine.py process
            cmd = f"ps -ef | grep '{task_id}' | grep 'engine.py' | grep -v grep | awk '{{print $2}}'"
            result = subprocess.check_output(cmd, shell=True).decode().strip()
            
            if result:
                pid = int(result)
                print(f"Found Python engine.py process with PID {pid} for task {task_id}")
                
                # Kill the process and its children
                print(f"Killing process {pid} and its children")
                if os.name != 'nt':  # Unix/Linux/MacOS
                    # try:
                    #     # Try to kill process group first
                    #     os.killpg(os.getpgid(pid), signal.SIGKILL)
                    #     print(f"Sent SIGKILL to process group for PID {pid}")
                    # except Exception as group_err:
                    #     print(f"Error killing process group: {str(group_err)}")
                        
                    # Also try direct kill commands
                    os.system(f"kill -9 {pid}")
                    os.system(f"pkill -P {pid}")  # Kill all child processes
                    print(f"Used kill commands on PID {pid}")
                else:
                    # Windows
                    os.system(f"taskkill /F /PID {pid} /T")
                    print(f"Used taskkill on PID {pid}")
            else:
                print(f"Could not find Python engine.py process for task {task_id}")
                
                # Fall back to looking for the run.sh process
                cmd = f"ps -ef | grep '{task_dir}/run.sh' | grep -v grep | awk '{{print $2}}'"
                result = subprocess.check_output(cmd, shell=True).decode().strip()
                
                if result:
                    pid = int(result)
                    print(f"Found run.sh process with PID {pid} for task {task_id}")
                    
                    # Kill the process
                    if os.name != 'nt':
                        os.system(f"kill -9 {pid}")
                        # os.system(f"pkill -P {pid}")
                    else:
                        os.system(f"taskkill /F /PID {pid} /T")
                else:
                    print(f"Could not find run.sh process for task {task_id}")
                    
        except Exception as e:
            print(f"Error finding or killing processes for task {task_id}: {str(e)}")
            
            # As a last resort, try to kill any processes related to the task directory
            if os.name != 'nt':
                os.system(f"pkill -f '{task_dir}'")
                print(f"Attempted to kill any processes related to {task_dir}")
        
        # Create a done file to indicate the task is stopped
        with open(os.path.join(task_dir, 'done.txt'), 'w') as f:
            f.write("Stopped by user at " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # Update task status
        task_storage[task_id]["status"] = "stopped"
        
        # Set a result message for stopped tasks
        task_storage[task_id]["result"] = "Task was stopped by user request before completion."
        
        # Emit a socket message to notify the frontend
        socketio.emit('task_update', {
            'taskId': task_id,
            'status': 'stopped',
            'message': 'Task has been stopped by user request'
        })
        
        return jsonify({
            "status": "ok",
            "message": f"Task {task_id} has been stopped"
        })
    except Exception as e:
        app.logger.error(f"Error stopping task {task_id}: {str(e)}")
        return jsonify({
            "status": "error",
            "error": f"Failed to stop task: {str(e)}"
        }), 500

@app.route('/api/delete-task/<task_id>', methods=['DELETE'])
def api_delete_task(task_id):
    """Delete a previously generated task and its associated files"""
    try:
        # Sanitize task_id to prevent path traversal
        if not re.match(r'^[a-zA-Z0-9_\-]+$', task_id):
            return jsonify({"status": "error", "error": "Invalid task ID format"}), 400
            
        # Define paths to check for task files
        task_dir = os.path.join(RESULTS_DIR, task_id)
        records_dir = os.path.join(RESULTS_DIR, 'records', task_id)
        
        deleted = False
        
        # Check and delete from main results directory
        if os.path.isdir(task_dir):
            shutil.rmtree(task_dir)
            deleted = True
            
        # Check and delete from records subdirectory
        if os.path.isdir(records_dir):
            shutil.rmtree(records_dir)
            deleted = True
            
        # If nothing was found to delete
        if not deleted:
            return jsonify({"status": "error", "error": "Task not found"}), 404
            
        # Remove from task storage if it exists
        if task_id in task_storage:
            del task_storage[task_id]
            
        return jsonify({
            "status": "ok",
            "message": f"Task {task_id} deleted successfully"
        })
    except Exception as e:
        app.logger.error(f"Error deleting task {task_id}: {str(e)}")
        return jsonify({
            "status": "error",
            "error": f"Failed to delete task: {str(e)}"
        }), 500

@app.route('/api/history', methods=['GET'])
def api_get_history():
    """Get a list of previously generated tasks with their basic info"""
    # Make sure task_storage is up to date
    reload_task_storage()
    
    history_tasks = []
    
    # List all directories in the results folder
    for task_id in os.listdir(RESULTS_DIR):
        task_dir = os.path.join(RESULTS_DIR, task_id)
        if not os.path.isdir(task_dir):
            continue
            
        # Check if this is a completed task with results
        result_file = os.path.join(task_dir, 'result.jsonl')
        if not os.path.exists(result_file):
            continue
            
        # Get the input file to extract the prompt
        input_file = os.path.join(task_dir, 'input.jsonl')
        prompt = ""
        task_type = "unknown"
        
        if os.path.exists(input_file):
            try:
                with open(input_file, 'r') as f:
                    input_data = json.load(f)
                    if 'value' in input_data:
                        # Story generation input
                        prompt = input_data.get('value', '')
                        task_type = "story"
                    elif 'prompt' in input_data:
                        # Report generation input
                        prompt = input_data.get('prompt', '')
                        task_type = "report"
            except:
                # If we can't read the input file, continue anyway
                pass
        
        # Get the creation time of the result file as timestamp
        creation_time = os.path.getctime(result_file)
        creation_date = datetime.fromtimestamp(creation_time).strftime('%Y-%m-%d %H:%M:%S')
        
        # Add task info to history list
        history_tasks.append({
            "taskId": task_id,
            "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt,
            "type": task_type,
            "createdAt": creation_date
        })
    
    # Sort by creation time, newest first
    history_tasks.sort(key=lambda x: x["createdAt"], reverse=True)
    
    return jsonify({
        "history": history_tasks
    })

@app.route('/api/workspace/<task_id>', methods=['GET'])
def api_get_workspace(task_id):
    """Get the article.txt content for a task"""
    task_dir = os.path.join(RESULTS_DIR, 'records', task_id)
    article_file = os.path.join(task_dir, 'article.txt')
    
    if not os.path.exists(article_file):
        return jsonify({"error": "Workspace file not found"}), 404
    
    try:
        with open(article_file, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({
            "taskId": task_id,
            "workspace": content
        })
    except Exception as e:
        print(f"Error reading workspace file: {str(e)}")
        return jsonify({"error": f"Failed to read workspace file: {str(e)}"}), 500

@app.route('/api/ping', methods=['GET'])
def api_ping():
    """Simple endpoint to test if the API is reachable"""
    return jsonify({
        "status": "ok",
        "message": "API server is running",
        "version": "1.0.0"
    })

# ======== 知识库 API 端点 ========

_kb_service = None
_kb_service_test = None  # For testData with 1024-dim embeddings


def _get_kb_service():
    global _kb_service
    if _kb_service is None:
        from recursive.knowledge_base import KnowledgeBaseService
        kb_base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge_bases')
        _kb_service = KnowledgeBaseService(base_path=kb_base_path)
    return _kb_service


TESTDATA_KB_NAME = "testdata"
TESTDATA_COLLECTION_NAME = "rag_chunks"
TESTDATA_EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"

LARGE_KB_NAME = "large_kb"
LARGE_KB_COLLECTION_NAME = "rag_chunks"
LARGE_KB_EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"


def _get_test_kb_service():
    """Get knowledge base service for testData (uses BAAI/bge-large-zh-v1.5 for 1024-dim vectors)."""
    global _kb_service_test
    if _kb_service_test is None:
        from recursive.knowledge_base.vector_store import ChromaVectorStore
        test_chroma_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'testdata', 'chroma_data'))
        _kb_service_test = ChromaVectorStore(
            persist_dir=test_chroma_path,
            embedding_model=TESTDATA_EMBEDDING_MODEL
        )
    return _kb_service_test


@app.route('/api/knowledge-base', methods=['GET'])
def api_list_knowledge_bases():
    """List all knowledge bases including the external testdata collection."""
    try:
        service = _get_kb_service()
        kbs = service.list_kbs()

        # Expose the external testdata Chroma database as a knowledge base
        testdata_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'testdata', 'chroma_data')
        if os.path.isdir(testdata_path):
            try:
                # Configure environment so vector_store can route "testdata" to the external DB
                testdata_abs_path = os.path.abspath(testdata_path)
                os.environ['WRITEHERE_KB_{}_PATH'.format(TESTDATA_KB_NAME.upper())] = testdata_abs_path
                os.environ['WRITEHERE_KB_{}_EMBEDDING'.format(TESTDATA_KB_NAME.upper())] = TESTDATA_EMBEDDING_MODEL

                # Get collection count without initializing embedding provider
                import chromadb
                _tmp_client = chromadb.PersistentClient(path=testdata_abs_path)
                _tmp_collection = _tmp_client.get_collection(name=TESTDATA_COLLECTION_NAME)
                testdata_chunk_count = _tmp_collection.count()

                kbs.insert(0, {
                    "name": TESTDATA_KB_NAME,
                    "created_at": None,
                    "updated_at": None,
                    "status": "ready",
                    "chunk_count": testdata_chunk_count,
                    "documents_dir": "",
                    "embedding_model": TESTDATA_EMBEDDING_MODEL,
                    "external": True,
                    "note": "External Chroma DB from testdata/chroma_data"
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                print("Failed to include testdata knowledge base: {}".format(e))

        # Expose the large external knowledge base
        large_kb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge_bases', 'large_kb', 'chroma_data')
        if os.path.isdir(large_kb_path):
            try:
                large_kb_abs_path = os.path.abspath(large_kb_path)
                os.environ['WRITEHERE_KB_{}_PATH'.format(LARGE_KB_NAME.upper())] = large_kb_abs_path
                os.environ['WRITEHERE_KB_{}_EMBEDDING'.format(LARGE_KB_NAME.upper())] = LARGE_KB_EMBEDDING_MODEL

                import chromadb
                _tmp_client2 = chromadb.PersistentClient(path=large_kb_abs_path)
                _tmp_collection2 = _tmp_client2.get_collection(name=LARGE_KB_COLLECTION_NAME)
                large_chunk_count = _tmp_collection2.count()

                kbs.insert(0, {
                    "name": LARGE_KB_NAME,
                    "created_at": None,
                    "updated_at": None,
                    "status": "ready",
                    "chunk_count": large_chunk_count,
                    "documents_dir": "",
                    "embedding_model": LARGE_KB_EMBEDDING_MODEL,
                    "external": True,
                    "note": "Large external KB (33K+ chunks)"
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                print("Failed to include large knowledge base: {}".format(e))

        return jsonify({"knowledgeBases": kbs})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/knowledge-base/<name>', methods=['GET'])
def api_get_knowledge_base(name):
    """Get details of a knowledge base."""
    try:
        if name == TESTDATA_KB_NAME:
            import chromadb
            testdata_abs_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'testdata', 'chroma_data'))
            _tmp_client = chromadb.PersistentClient(path=testdata_abs_path)
            _tmp_collection = _tmp_client.get_collection(name=TESTDATA_COLLECTION_NAME)
            return jsonify({
                "name": TESTDATA_KB_NAME,
                "created_at": None,
                "updated_at": None,
                "status": "ready",
                "chunk_count": _tmp_collection.count(),
                "documents_dir": "",
                "embedding_model": TESTDATA_EMBEDDING_MODEL,
                "external": True,
                "note": "External Chroma DB from testdata/chroma_data"
            })
        if name == LARGE_KB_NAME:
            import chromadb
            large_kb_abs_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge_bases', 'large_kb', 'chroma_data'))
            _tmp_client = chromadb.PersistentClient(path=large_kb_abs_path)
            _tmp_collection = _tmp_client.get_collection(name=LARGE_KB_COLLECTION_NAME)
            return jsonify({
                "name": LARGE_KB_NAME,
                "created_at": None,
                "updated_at": None,
                "status": "ready",
                "chunk_count": _tmp_collection.count(),
                "documents_dir": "",
                "embedding_model": LARGE_KB_EMBEDDING_MODEL,
                "external": True,
                "note": "Large external KB (33K+ chunks from knowledge_bases/large_kb)"
            })
        service = _get_kb_service()
        meta = service.get_kb(name)
        if not os.path.exists(service._kb_dir(name)):
            return jsonify({"error": "Knowledge base not found"}), 404
        return jsonify(meta)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/knowledge-base/<name>', methods=['DELETE'])
def api_delete_knowledge_base(name):
    """Delete a knowledge base."""
    try:
        service = _get_kb_service()
        service.delete_kb(name)
        return jsonify({"message": "Knowledge base deleted", "name": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/knowledge-base/<name>/index', methods=['POST'])
def api_index_knowledge_base(name):
    """Re-index all documents in a knowledge base."""
    try:
        service = _get_kb_service()
        def do_index():
            try:
                service.reindex(name)
            except Exception as e:
                logger.error("Failed to reindex knowledge base {}: {}".format(name, e))
        thread = threading.Thread(target=do_index)
        thread.start()
        return jsonify({"name": name, "status": "indexing_started"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/knowledge-base/upload', methods=['POST'])
def api_upload_knowledge_base():
    """Upload files to a knowledge base and index them."""
    try:
        name = request.form.get('knowledgeBaseName', '').strip()
        if not name:
            return jsonify({"error": "knowledgeBaseName is required"}), 400

        files = request.files.getlist('files[]')
        if not files:
            return jsonify({"error": "No files uploaded"}), 400

        service = _get_kb_service()
        docs_dir = service._docs_dir(name)
        os.makedirs(docs_dir, exist_ok=True)

        saved_paths = []
        for file in files:
            if not file.filename:
                continue
            save_path = os.path.join(docs_dir, file.filename)
            file.save(save_path)
            saved_paths.append(save_path)

        if not saved_paths:
            return jsonify({"error": "No valid files uploaded"}), 400

        def do_index():
            try:
                service.process_and_index(name)
            except Exception as e:
                logger.error("Failed to index knowledge base {}: {}".format(name, e))

        thread = threading.Thread(target=do_index)
        thread.start()

        return jsonify({
            "knowledgeBaseName": name,
            "uploadedFiles": [os.path.basename(p) for p in saved_paths],
            "status": "indexing",
            "message": "Files uploaded, indexing in background."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/knowledge-base/<name>/search', methods=['POST'])
def api_search_knowledge_base(name):
    """Search a knowledge base directly."""
    try:
        data = request.json or {}
        query = data.get('query', '')
        topk = data.get('topk', 5)
        if not query:
            return jsonify({"error": "query is required"}), 400

        if name == TESTDATA_KB_NAME:
            store = _get_test_kb_service()
            results = store.search(TESTDATA_COLLECTION_NAME, query, topk=topk)
            return jsonify({
                "knowledgeBaseName": name,
                "query": query,
                "embedding_model": TESTDATA_EMBEDDING_MODEL,
                "results": results
            })

        service = _get_kb_service()
        results = service.search(name, query, topk=topk)
        return jsonify({"knowledgeBaseName": name, "query": query, "results": results})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/test-knowledge-base/search', methods=['POST'])
def api_search_test_knowledge_base():
    """Search the testData knowledge base (rag_chunks collection with 1024-dim embeddings)."""
    try:
        data = request.json or {}
        query = data.get('query', '')
        topk = data.get('topk', 5)
        if not query:
            return jsonify({"error": "query is required"}), 400

        # Use test service with BAAI/bge-large-zh-v1.5
        service = _get_test_kb_service()
        results = service.search('rag_chunks', query, topk=topk)

        return jsonify({
            "knowledgeBaseName": "testData/rag_chunks",
            "query": query,
            "embedding_model": "BAAI/bge-large-zh-v1.5 (1024-dim)",
            "results": results
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ======== 评估系统 API 端点 ========

@app.route('/api/evaluations/latest', methods=['GET'])
def api_get_latest_evaluations():
    """获取两个Agent的最新评估结果对比"""
    import json
    from pathlib import Path

    eval_base = os.path.join(os.path.dirname(__file__), '..', 'recursive', 'evaluation')
    results_dir = Path(eval_base) / 'results'

    writehere_dir = results_dir / 'writehere'
    wh_eval = None
    if writehere_dir.exists():
        wh_files = sorted(writehere_dir.glob('eval_writehere_*.json'))
        if wh_files:
            with open(wh_files[-1], 'r', encoding='utf-8') as f:
                wh_eval = json.load(f)

    # 尝试加载Mo-Shen评估
    mo_shen_dir = Path(eval_base).parent.parent / '..' / '..' / 'Mo-Shen-main' / 'storyagents' / 'evaluation' / 'results' / 'mo_shen'
    ms_eval = None
    if mo_shen_dir.exists():
        ms_files = sorted(mo_shen_dir.glob('eval_summary_*.json'))
        if ms_files:
            with open(ms_files[-1], 'r', encoding='utf-8') as f:
                ms_eval = json.load(f)

    return jsonify({
        'writehere': wh_eval,
        'mo_shen': ms_eval,
        'success': True
    })

@app.route('/api/evaluations/<agent_type>/latest', methods=['GET'])
def api_get_agent_evaluation(agent_type):
    """获取指定Agent的最新评估结果"""
    import json
    from pathlib import Path

    eval_base = os.path.join(os.path.dirname(__file__), '..', 'recursive', 'evaluation')
    results_dir = Path(eval_base) / 'results' / agent_type

    if not results_dir.exists():
        return jsonify({'error': f'No evaluations found for {agent_type}', 'success': False}), 404

    glob_pattern = f'eval_{agent_type}_*.json'
    eval_files = sorted(results_dir.glob(glob_pattern))

    if not eval_files:
        return jsonify({'error': f'No evaluation files found for {agent_type}', 'success': False}), 404

    with open(eval_files[-1], 'r', encoding='utf-8') as f:
        eval_data = json.load(f)

    return jsonify({
        'evaluation': eval_data,
        'success': True
    })

@app.route('/api/evaluations/compare', methods=['GET'])
def api_compare_evaluations():
    """对比WriteHERE和Mo-Shen的评估结果"""
    import json
    from pathlib import Path

    eval_base = os.path.join(os.path.dirname(__file__), '..', 'recursive', 'evaluation')
    results_dir = Path(eval_base) / 'results'

    def load_latest(agent_dir):
        d = results_dir / agent_dir
        if not d.exists():
            return None
        files = sorted(d.glob(f'eval_{agent_dir}_*.json'))
        if not files:
            return None
        with open(files[-1], 'r', encoding='utf-8') as f:
            return json.load(f)

    writehere = load_latest('writehere')
    mo_shen = load_latest('mo_shen')

    if not writehere:
        return jsonify({'error': 'No WriteHERE evaluation data', 'success': False}), 404

    comparison = {
        'writehere': {
            'step_level_score': writehere.get('overall_step_level_score', 0),
            'trajectory_level_score': writehere.get('overall_trajectory_level_score', 0),
            'llm_accuracy': writehere.get('llm_call_accuracy', 0),
            'tool_accuracy': writehere.get('tool_call_accuracy', 0),
            'rationality_score': writehere.get('avg_rationality_score', 0),
            'efficiency_score': writehere.get('avg_efficiency_score', 0),
            'success_rate': writehere.get('trajectory_success_rate', 0),
            'avg_duration_s': writehere.get('avg_trajectory_duration_ms', 0) / 1000
        },
        'mo_shen': {
            'step_level_score': mo_shen.get('overall_step_level_score', 0) if mo_shen else 0,
            'trajectory_level_score': mo_shen.get('overall_trajectory_level_score', 0) if mo_shen else 0,
            'llm_accuracy': mo_shen.get('llm_call_accuracy', 0) if mo_shen else 0,
            'tool_accuracy': mo_shen.get('tool_call_accuracy', 0) if mo_shen else 0,
            'rationality_score': mo_shen.get('avg_rationality_score', 0) if mo_shen else 0,
            'efficiency_score': mo_shen.get('avg_efficiency_score', 0) if mo_shen else 0,
            'success_rate': mo_shen.get('trajectory_success_rate', 0) if mo_shen else 0,
            'avg_duration_s': mo_shen.get('avg_trajectory_duration_ms', 0) / 1000 if mo_shen else 0
        },
        'success': True
    }

    # 确定各项指标的优胜者
    metrics = ['step_level_score', 'trajectory_level_score', 'llm_accuracy',
               'tool_accuracy', 'rationality_score', 'efficiency_score', 'success_rate']
    winners = {}
    for metric in metrics:
        wh_val = comparison['writehere'].get(metric, 0)
        ms_val = comparison['mo_shen'].get(metric, 0)
        winners[metric] = 'writehere' if wh_val > ms_val else ('mo_shen' if ms_val > wh_val else 'tie')

    wh_dur = comparison['writehere'].get('avg_duration_s', 0)
    ms_dur = comparison['mo_shen'].get('avg_duration_s', 0)
    winners['avg_duration_s'] = 'writehere' if wh_dur < ms_dur else ('mo_shen' if ms_dur < wh_dur else 'tie')

    comparison['winners'] = winners
    return jsonify(comparison)

# ======== 评估系统 API 端点结束 ========

def monitor_task_progress(task_id, nodes_dir):
    """
    Monitor task progress and send updates via WebSocket
    """
    try:
        print(f"Starting task progress monitoring for task: {task_id}")
        print(f"Monitoring directory: {nodes_dir}")
        
        # Create a basic task structure to start with
        task_graph = {
            "id": "0",
            "goal": "Initializing task...",
            "task_type": "think",
            "status": "DOING",
            "sub_tasks": []
        }
        
        print(f"Sending initial task_update for {task_id}")
        socketio.emit('task_update', {'taskId': task_id, 'taskGraph': task_graph})
        
        # Monitor the nodes.json file for changes
        last_modified = 0
        nodes_file = os.path.join(nodes_dir, 'nodes.json')
        task_dir = os.path.dirname(nodes_dir)
        print(f"Watching for changes to: {nodes_file}")
        
        while task_storage.get(task_id, {}).get('status') not in ['completed', 'error', 'stopped']:                
            if os.path.exists(nodes_file):
                current_modified = os.path.getmtime(nodes_file)
                
                if current_modified > last_modified:
                    last_modified = current_modified
                    print(f"Detected changes to nodes.json, reading file")
                    
                    try:
                        with open(nodes_file, 'r') as f:
                            nodes_data = json.load(f)
                        
                        # Transform the data for frontend
                        transformed_graph = transform_node_to_graph(nodes_data, root=True)
                        
                        # Send update via WebSocket
                        print(f"Sending task_update with {len(transformed_graph.get('sub_tasks', []))} sub-tasks")
                        
                        # Debug output - check if we have action information
                        if 'latest_action' in transformed_graph:
                            print(f"Root node has latest action: {transformed_graph['latest_action']['name']}")
                        
                        # Debug the first subtask if available
                        if transformed_graph.get('sub_tasks') and len(transformed_graph.get('sub_tasks', [])) > 0:
                            first_task = transformed_graph['sub_tasks'][0]
                            if 'latest_action' in first_task:
                                print(f"First subtask has latest action: {first_task['latest_action']['name']}")
                        
                        socketio.emit('task_update', {
                            'taskId': task_id, 
                            'taskGraph': transformed_graph
                        })
                    except Exception as e:
                        print(f"Error reading nodes.json: {str(e)}")
            else:
                print(f"Waiting for nodes.json file to be created at: {nodes_file}")
            
            # Sleep for a short time to avoid high CPU usage
            time.sleep(1)
            
        print(f"Task {task_id} status changed to {task_storage.get(task_id, {}).get('status')}")
        # Send one final update once the task is complete
        if os.path.exists(nodes_file):
            try:
                print(f"Reading final state from nodes.json")
                with open(nodes_file, 'r') as f:
                    nodes_data = json.load(f)
                    
                transformed_graph = transform_node_to_graph(nodes_data, root=True)
                print(f"Sending final task_update with status {task_storage.get(task_id, {}).get('status')}")
                socketio.emit('task_update', {
                    'taskId': task_id, 
                    'taskGraph': transformed_graph,
                    'status': task_storage.get(task_id, {}).get('status', 'unknown')
                })
            except Exception as e:
                print(f"Error reading final nodes.json: {str(e)}")
        else:
            print(f"Warning: nodes.json file not found for final update: {nodes_file}")
    
    except Exception as e:
        print(f"Error in monitor_task_progress: {str(e)}")
        import traceback
        print(traceback.format_exc())

# Socket.IO event handlers
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    # Send a test message to verify the connection works
    socketio.emit('connection_test', {'message': 'Connected successfully to the server'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('subscribe_to_task')
def handle_subscribe(data):
    print(f"Received subscription request: {data}")
    task_id = data.get('taskId')
    
    if not task_id:
        print("No taskId provided in subscription request")
        emit('subscription_status', {'status': 'error', 'message': 'No taskId provided', 'taskId': None})
        return
        
    print(f"Checking if task {task_id} exists in storage")
    # Always allow subscription, even if task doesn't exist yet (it might be starting)
    task_dir = os.path.join(RESULTS_DIR, task_id)
    nodes_dir = os.path.join(task_dir, 'records')
    
    if not os.path.exists(nodes_dir):
        print(f"Creating nodes directory: {nodes_dir}")
        os.makedirs(nodes_dir, exist_ok=True)
    
    # Start monitoring in a background thread
    print(f"Starting monitoring thread for task {task_id}")
    thread = threading.Thread(
        target=monitor_task_progress,
        args=(task_id, nodes_dir)
    )
    thread.daemon = True
    thread.start()
    
    print(f"Sending subscription confirmation for {task_id}")
    emit('subscription_status', {'status': 'subscribed', 'taskId': task_id})
    
    # Also send an initial update to confirm the subscription worked
    initial_graph = {
        "id": "0",
        "goal": "Task is initializing...",
        "task_type": "think",
        "status": "READY",
        "sub_tasks": []
    }
    emit('task_update', {'taskId': task_id, 'taskGraph': initial_graph})

if __name__ == '__main__':
    socketio.run(app, debug=True, host="0.0.0.0", port=args.port, allow_unsafe_werkzeug=True)


@app.route('/api/evaluations/latest', methods=['GET'])
def get_latest_evaluations():
    """Get latest evaluation results for both agents"""
    import json
    from pathlib import Path

    results_dir = Path('./evaluation/results')

    # Find latest WriteHERE evaluation
    writehere_files = sorted(results_dir.glob('writehere/eval_writehere_*.json'))
    mo_shen_files = sorted(results_dir.glob('mo_shen/eval_mo_shen_*.json'))

    writehere_eval = None
    mo_shen_eval = None

    if writehere_files:
        with open(writehere_files[-1], 'r', encoding='utf-8') as f:
            writehere_eval = json.load(f)

    if mo_shen_files:
        with open(mo_shen_files[-1], 'r', encoding='utf-8') as f:
            mo_shen_eval = json.load(f)

    return jsonify({
        'writehere': writehere_eval,
        'mo_shen': mo_shen_eval,
        'success': True
    })


@app.route('/api/evaluations/<agent_type>/latest', methods=['GET'])
def get_agent_evaluation(agent_type):
    """Get latest evaluation for a specific agent"""
    import json
    from pathlib import Path

    results_dir = Path('./evaluation/results') / agent_type

    if not results_dir.exists():
        return jsonify({'error': f'No evaluations found for {agent_type}', 'success': False}), 404

    eval_files = sorted(results_dir.glob(f'eval_{agent_type}_*.json'))

    if not eval_files:
        return jsonify({'error': f'No evaluation files found', 'success': False}), 404

    with open(eval_files[-1], 'r', encoding='utf-8') as f:
        eval_data = json.load(f)

    return jsonify({
        'evaluation': eval_data,
        'success': True
    })


@app.route('/api/evaluations/compare', methods=['GET'])
def compare_evaluations():
    """Compare evaluations between WriteHERE and Mo-Shen"""
    import json
    from pathlib import Path

    results_dir = Path('./evaluation/results')

    # Find latest evaluations
    writehere_files = sorted(results_dir.glob('writehere/eval_writehere_*.json'))
    mo_shen_files = sorted(results_dir.glob('mo_shen/eval_mo_shen_*.json'))

    if not writehere_files or not mo_shen_files:
        return jsonify({'error': 'Missing evaluation data', 'success': False}), 404

    with open(writehere_files[-1], 'r', encoding='utf-8') as f:
        writehere = json.load(f)

    with open(mo_shen_files[-1], 'r', encoding='utf-8') as f:
        mo_shen = json.load(f)

    # Create comparison
    comparison = {
        'writehere': {
            'step_level_score': writehere.get('overall_step_level_score', 0),
            'trajectory_level_score': writehere.get('overall_trajectory_level_score', 0),
            'llm_accuracy': writehere.get('llm_call_accuracy', 0),
            'tool_accuracy': writehere.get('tool_call_accuracy', 0),
            'rationality_score': writehere.get('avg_rationality_score', 0),
            'efficiency_score': writehere.get('avg_efficiency_score', 0),
            'success_rate': writehere.get('trajectory_success_rate', 0),
            'avg_duration_s': writehere.get('avg_trajectory_duration_ms', 0) / 1000
        },
        'mo_shen': {
            'step_level_score': mo_shen.get('overall_step_level_score', 0),
            'trajectory_level_score': mo_shen.get('overall_trajectory_level_score', 0),
            'llm_accuracy': mo_shen.get('llm_call_accuracy', 0),
            'tool_accuracy': mo_shen.get('tool_call_accuracy', 0),
            'rationality_score': mo_shen.get('avg_rationality_score', 0),
            'efficiency_score': mo_shen.get('avg_efficiency_score', 0),
            'success_rate': mo_shen.get('trajectory_success_rate', 0),
            'avg_duration_s': mo_shen.get('avg_trajectory_duration_ms', 0) / 1000
        }
    }

    # Determine winner for each metric
    metrics = ['step_level_score', 'trajectory_level_score', 'llm_accuracy',
               'tool_accuracy', 'rationality_score', 'efficiency_score', 'success_rate']

    comparison['winners'] = {}
    for metric in metrics:
        wh_val = comparison['writehere'].get(metric, 0)
        ms_val = comparison['mo_shen'].get(metric, 0)
        if wh_val > ms_val:
            comparison['winners'][metric] = 'writehere'
        elif ms_val > wh_val:
            comparison['winners'][metric] = 'mo_shen'
        else:
            comparison['winners'][metric] = 'tie'

    # Duration is lower=better
    wh_dur = comparison['writehere'].get('avg_duration_s', 0)
    ms_dur = comparison['mo_shen'].get('avg_duration_s', 0)
    if wh_dur < ms_dur:
        comparison['winners']['avg_duration_s'] = 'writehere'
    elif ms_dur < wh_dur:
        comparison['winners']['avg_duration_s'] = 'mo_shen'
    else:
        comparison['winners']['avg_duration_s'] = 'tie'

    comparison['success'] = True

    return jsonify(comparison)
