from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .gemini_ai import parse_expense_text, plan_project, review_code


@api_view(["POST"])
def parse_expense(request):
    text = request.data.get("text", "")
    if not text:
        return Response(
            {"error": "text is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    result = parse_expense_text(text)
    if not result:
        return Response(
            {"error": "Could not parse expense data"},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return Response(result)


@api_view(["POST"])
def plan_project_view(request):
    description = request.data.get("description", "")
    if not description:
        return Response(
            {"error": "description is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    result = plan_project(description)
    if not result:
        return Response(
            {"error": "Could not generate project plan"},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return Response(result)


@api_view(["POST"])
def review_code_view(request):
    source_files = request.data.get("source_files", {})
    test_results = request.data.get("test_results", "")

    if not source_files:
        return Response(
            {"error": "source_files is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    result = review_code(source_files, test_results)
    if not result:
        return Response(
            {"error": "Could not generate code review"},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return Response(result)
