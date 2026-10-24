import json, sys
from .data import generate_data
from .tools import ToolSuite
from .agent import RefundAgent

def main():
    generate_data()
    question = " ".join(sys.argv[1:]) or input("Question: ")
    result = RefundAgent(ToolSuite(), verifier_enabled=True).answer(question)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
