import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "--cov=doc_parser", "--cov-report=term", "-q"],
    capture_output=True,
    text=True,
    cwd=r"e:\Work\PJC\Github\ppdocs",
)
print("STDOUT:")
print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
print("STDERR:")
print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
print(f"Return code: {result.returncode}")
