import types


def ordinary():
    return 3


def test_native():
    return ordinary()


def exercise():
    ordinary()
    test_native()
    for name in ("test\ud800", "\ud800", "runTest", "normalé"):
        types.FunctionType(ordinary.__code__.replace(co_name=name), globals())()
