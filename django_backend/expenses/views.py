from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Sum
from django.utils import timezone
import datetime

from .models import Expense, Category, User
from .serializers import ExpenseSerializer, ExpenseCreateSerializer, CategorySerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.select_related("category", "user").all()
    serializer_class = ExpenseSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return ExpenseCreateSerializer
        return ExpenseSerializer

    def create(self, request, *args, **kwargs):
        create_serializer = ExpenseCreateSerializer(data=request.data)
        create_serializer.is_valid(raise_exception=True)
        data = create_serializer.validated_data

        user, _ = User.objects.get_or_create(
            id=1, defaults={"email": "default@example.com", "hashed_password": ""}
        )

        category_id = data.pop("category_id", None)
        expense = Expense.objects.create(user=user, category_id=category_id, **data)
        response_serializer = ExpenseSerializer(expense)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="summary")
    def monthly_summary(self, request):
        now = timezone.now()
        start_of_month = datetime.datetime(now.year, now.month, 1, tzinfo=timezone.utc)

        summary = (
            Expense.objects.filter(date__gte=start_of_month)
            .values("category_id")
            .annotate(total=Sum("amount"))
        )

        return Response(
            [{"category_id": row["category_id"], "total": row["total"]} for row in summary]
        )

    @action(detail=False, methods=["post"], url_path="parse-text")
    def parse_text(self, request):
        from ai_services.gemini_ai import parse_expense_text

        text = request.data.get("text", "")
        if not text:
            return Response(
                {"error": "text is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        parsed = parse_expense_text(text)
        if not parsed:
            return Response(
                {"error": "Could not parse expense"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, _ = User.objects.get_or_create(
            id=1, defaults={"email": "default@example.com", "hashed_password": ""}
        )

        expense = Expense.objects.create(
            user=user,
            amount=parsed.get("amount", 0),
            description=parsed.get("merchant", ""),
            ai_label=parsed.get("category", ""),
        )

        response_serializer = ExpenseSerializer(expense)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=["post"],
        url_path="upload",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_receipt(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response(
                {"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST
            )

        from ai_services.gemini_ai import parse_receipt_image

        content = file.read()
        content_type = file.content_type or "image/jpeg"

        parsed_data = parse_receipt_image(content, content_type)

        if not parsed_data:
            return Response(
                {"error": "Could not parse receipt"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, _ = User.objects.get_or_create(
            id=1, defaults={"email": "default@example.com", "hashed_password": ""}
        )

        expense = Expense.objects.create(
            user=user,
            amount=parsed_data.get("amount", 0),
            description=parsed_data.get("merchant", ""),
            ai_label=parsed_data.get("category", ""),
        )

        response_serializer = ExpenseSerializer(expense)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
