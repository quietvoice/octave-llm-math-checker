import subprocess
import sys
from openai import OpenAI

client = OpenAI(api_key="")
statement1 = "9.11と9.9どちらが大きいか？"
stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": statement1}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")

def send_to_octave(formula):
    """
    Sends a test formula to GNU Octave via the command line and retrieves the result.

    Args:
        formula (str): The mathematical formula to evaluate in Octave.

    Returns:
        str: The output from Octave.
    """
    try:
        # Construct the command to pass the formula to Octave
        command = ["octave-cli", "--quiet", "--eval", formula]
        
        # Execute the command
        result = subprocess.run(command, text=True, capture_output=True)

        # Check for errors
        if result.returncode != 0:
            print("Error in executing Octave command:", result.stderr)
            return None

        return result.stdout.strip()

    except Exception as e:
        print("Exception occurred:", str(e))
        return None

# Example usage
if __name__ == "__main__":
    #test: 9.99 > 9.11
    #
    formula = sys.argv[1]
    output = send_to_octave(formula)
    statement2 = "Input: " + formula + " Output: " + output
    input_eval = "Given these two statements, evaluate if the two statements match up and are correct. If it is wrong, explain where is wrong. Statement2's ans=1 means true and ans=0 means false." + "Statement 1: " + statement1 + "Statement 2:" + statement2 
    stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": input_eval}],
    stream=True,
    )
    for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            print(chunk.choices[0].delta.content, end="")
