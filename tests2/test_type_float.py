


def test_float():
    x = 1.0
    assert x == 1.0

    y = 1.0
    y += 2.0
    assert y > 2.5

    assert float('+1.23') == 1.23
    assert float('-1.23') == -1.23
    assert float(1) == 1.0


def test_all():
    test_float()


if __name__ == "__main__":
    test_all()