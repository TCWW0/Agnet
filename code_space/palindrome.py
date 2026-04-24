def is_palindrome(text: str) -> bool:
    """
    判断字符串是否为回文，忽略大小写与非字母数字字符。
    
    Args:
        text: 输入的字符串
        
    Returns:
        bool: 如果是回文返回 True，否则返回 False
    """
    # 提取所有字母数字字符（保留原大小写，但比较时转为小写）
    filtered = ''.join(c.lower() for c in text if c.isalnum())
    # 判断是否为回文
    return filtered == filtered[::-1]


if __name__ == "__main__":
    # 最小测试示例
    test_cases = [
        ("A man, a plan, a canal: Panama", True),
        ("race a car", False),
        ("Was it a car or a cat I saw", True),
        ("", True),
        ("a", True),
        ("ab", False),
        ("Madam", True),
        ("Hello, World!", False),
    ]
    
    for text, expected in test_cases:
        result = is_palindrome(text)
        status = "✓" if result == expected else "✗"
        print(f"{status} is_palindrome({text!r}) = {result} (expected {expected})")