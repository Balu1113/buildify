from llm.client import generate_response


def test_generate_response():
    response = generate_response(
        "Hello"
    )

    assert response is not None