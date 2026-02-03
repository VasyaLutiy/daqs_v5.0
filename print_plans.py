import json
import sys

def print_plans(json_file):
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        plans = data.get('plans', [])
        total = data.get('total', len(plans))
        
        print(f"Total plans found: {total}\n")
        
        for i, plan in enumerate(plans, 1):
            print(f"Plan {i}:")
            for j, step in enumerate(plan, 1):
                print(f"  {j}. {step}")
            print()  # Empty line between plans
    
    except FileNotFoundError:
        print(f"Error: File '{json_file}' not found.")
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in '{json_file}'.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python print_plans.py <json_file>")
        sys.exit(1)
    
    json_file = sys.argv[1]
    print_plans(json_file)