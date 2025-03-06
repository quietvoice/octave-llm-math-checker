# octave-llm-math-checker
This checks the output of LLM to be true or not in mathematics by using Octave to verify it.

It did not work as expected using OpenAI's GPT-4o, but with other models, the results may change. (We hope it does too.) 

This is a experiment, and we look forward for people forking it or doing on other models using Ollama etc.

Update: Ollama Test Version has been uploaded. It is under the ollama folder.

On an experiment we did by trying to use Octave as a verification tool to check the answer of a LLM math problem that is hard to solve by current LLM. We used GPT-4o for the experiment. The date of this experiment took place on 3/6/2025 around 7:54AM JST.

We used the standard OpenAI library with the model gpt-4o. 

We expected the model to correctly identify 9.9 as being greater than 9.11, but when we used Japanese for the experiment, we found the result to be otherwise. (We tested several times in other situations and 9.9 was outputted as being greater.)

We ran this code:

```
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
```

Output when script ran using this argument:

python3 octave-llm3.py "9.9 > 9.11"

```
9.11の方が大きいです。数字の比較では、小数点以下の数字を左から順に比較し、最初に異なる数字が出た時点で大小を判断します。9.1と9.9では1と9を比較し、9.9の方が大きいと判断できますが、これは解釈の誤りですので、正しく比較するために、9.11の1と9.9の最初の9を比較すればよく、9.9の方が大きいとも解釈されています（日本語では）。ただし、9.11は数学的には厳密に大きいです。

言語ごとにコンマや点の解釈が異なるため、9.9の方が制約されない大きな値として考えられる場合もありますが、通常は9.10へと展開されます。

これが混乱させる要因となり得ますが、基本的には9.11 > 9.9と受け取ることが安全です。The two statements do not match up correctly.

Statement 1 asks which is larger between 9.11 and 9.9. The correct mathematical comparison is that 9.11 is greater than 9.9. 

Statement 2, however, presents the inequality "9.9 > 9.11" and marks it as true by setting "ans = 1". This is incorrect, as 9.9 is actually less than 9.11.

Therefore, the error lies in Statement 2, where "9.9 > 9.11" should actually be false. Instead, it should say "9.9 < 9.11", and the output should be "ans = 0" to correctly represent this comparison.

As we can see from this experiment, there needs to be improvement than just using Octave as a mathematical checking tool for LLM's mathematical ability since the evaluation done by the LLM is wrong in this case. Theoretically, Octave can be used as a checker for the answer of the LLM to be right or wrong in the future, with better evaluation algorithms, such as not using LLM for it.
```

(C)Tsubasa Kato - Curioforce Corporation 2025/3/6 8:06AM
