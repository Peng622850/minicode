def fibonacci(n):
    """
    生成斐波那契数列的前n项
    """
    fib_sequence = []
    a, b = 0, 1
    for _ in range(n):
        fib_sequence.append(a)
        a, b = b, a + b
    return fib_sequence

if __name__ == "__main__":
    n = 10  # 指定斐波那契数列的项数为10
    print(f"斐波那契数列的前{n}项是: {fibonacci(n)}")