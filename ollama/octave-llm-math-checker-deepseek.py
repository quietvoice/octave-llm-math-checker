#Test Version using deepseek-math-7b-rl & deepseek-r1 on Ollama
#(C)Tsubasa Kato - 2025/3/6 19:13PM JST
import subprocess
import sys
import ollama

def ask_ollama(model, prompt):
    """
    Queries Ollama using the official Python library and streams the response.

    Args:
        model (str): The name of the Ollama model to use.
        prompt (str): The input prompt to send to the model.

    Returns:
        None
    """
    try:
        response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}], stream=True)
        for chunk in response:
            if "message" in chunk and "content" in chunk["message"]:
                print(chunk["message"]["content"], end="", flush=True)
    except Exception as e:
        print("\n[Error] Ollama request failed:", str(e))


def send_to_octave(formula):
    """
    Sends a formula to GNU Octave via the command line and retrieves the result.

    Args:
        formula (str): The mathematical formula to evaluate in Octave.

    Returns:
        str: The output from Octave.
    """
    try:
        command = ["octave-cli", "--quiet", "--eval", formula]
        result = subprocess.run(command, text=True, capture_output=True, shell=False)

        if result.returncode != 0:
            print("[Error] Octave command failed:", result.stderr)
            return None

        return result.stdout.strip()

    except Exception as e:
        print("[Exception] Error in send_to_octave:", str(e))
        return None


if __name__ == "__main__":
    statement1 = "Which is greater, 9.9 or 9.11"
    print("Ollama response to Statement 1:")
    ask_ollama("t1c/deepseek-math-7b-rl", statement1)
    print("\n")

    if len(sys.argv) < 2:
        print("[Error] No formula provided. Usage: python script.py '<formula>'")
        sys.exit(1)

    formula = sys.argv[1]
    output = formula + "'s result is: " + send_to_octave(formula)
    print(output)
    statement2 = f"Input: {formula} Output: {output if output else 'Error'}"
    input_eval = (
    "Determine whether Sentence 1 and Sentence 2 have the same meaning. If they do not, explain what the difference is. "
    "In Sentence 2, ans = 1 means True and ans = 0 means False."
    f" Sentence 1: {statement1} Sentence 2: {statement2}"
)

    print("\nOllama evaluation response:")
    ask_ollama("deepseek-r1", input_eval)
    print()
