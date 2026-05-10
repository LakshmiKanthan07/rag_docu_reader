import sys
import json
from pathlib import Path
from networkx.readwrite import json_graph
import networkx as nx

# Add local path to sys.path if needed
sys.path.append(str(Path('.').absolute()))

from graphify.report import generate
from graphify.analyze import god_nodes, surprising_connections, suggest_questions

def finish():
    out_dir = Path('graphify-out')
    graph_path = out_dir / 'graph.json'
    analysis_path = out_dir / '.graphify_analysis.json'
    detect_path = out_dir / 'manifest.json' # Using manifest as detection fallback

    if not graph_path.exists():
        print(f"Error: {graph_path} not found")
        return

    # Load graph
    with open(graph_path) as f:
        data = json.load(f)
    G = json_graph.node_link_graph(data, edges='links')

    # Load analysis
    if analysis_path.exists():
        with open(analysis_path) as f:
            analysis = json.load(f)
    else:
        print("Error: .graphify_analysis.json not found")
        return

    # Detection data fallback
    detection = {}
    if detect_path.exists():
        with open(detect_path) as f:
            manifest = json.load(f)
            detection = {
                'total_files': len(manifest),
                'total_words': 0, # Placeholder
                'files': {'code': [f for f in manifest if f.endswith('.py') or f.endswith('.js')], 'docs': []}
            }

    # Labels
    labels = {
        "0": "Core Backend & Vector Cache",
        "1": "Document Upload Verification",
        "2": "Chat Interaction Testing",
        "3": "Frontend UI & Components",
        "4": "System Configuration & Middleware Tests",
        "5": "Data Models & Auth API",
        "6": "Shared Test Fixtures",
        "7": "Vectorstore Retrieval & Persistence",
        "8": "Session Management Testing",
        "9": "Document Parsing & Formatting",
        "10": "Application Setup Tests",
        "11": "Cloud Storage & Async Tasks",
        "12": "Security & Authentication Logic",
        "13": "API Authentication Dependencies",
        "14": "Database Connectivity",
        "15": "Background Task Orchestration",
        "16": "Test Suite Initialization"
    }
    
    # Int labels for logic
    int_labels = {int(k): v for k, v in labels.items()}
    communities = {int(k): v for k, v in analysis['communities'].items()}
    cohesion = {int(k): v for k, v in analysis['cohesion'].items()}
    
    # Analyze
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    questions = suggest_questions(G, communities, int_labels)
    
    tokens = analysis.get('tokens', {'input': 0, 'output': 0})
    
    # Generate report
    report = generate(G, communities, cohesion, int_labels, gods, surprises, detection, tokens, '.', suggested_questions=questions)
    (out_dir / 'GRAPH_REPORT.md').write_text(report, encoding='utf-8')
    
    # Save labels for visualizer
    (out_dir / '.graphify_labels.json').write_text(json.dumps(labels), encoding='utf-8')
    
    # Update analysis file with new questions
    analysis['questions'] = questions
    analysis_path.write_text(json.dumps(analysis, indent=2), encoding='utf-8')
    
    print("Graph finishing complete.")
    print(f"Report: {out_dir / 'GRAPH_REPORT.md'}")
    print(f"Labels: {out_dir / '.graphify_labels.json'}")

if __name__ == "__main__":
    finish()
