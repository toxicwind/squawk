import json

def fibonacci(n):
    """Generate first n Fibonacci numbers."""
    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[i-1] + fib[i-2])
    return fib[:n]

# Compute first 20 Fibonacci numbers
result = fibonacci(20)

# Output as JSON
print(json.dumps(result))
