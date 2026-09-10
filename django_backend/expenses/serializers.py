from rest_framework import serializers
from .models import User, Category, Expense


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            "id",
            "amount",
            "date",
            "description",
            "ai_label",
            "user",
            "category",
            "category_name",
            "created_at",
        ]
        read_only_fields = ["id", "date", "created_at"]

    def get_category_name(self, obj):
        if obj.category:
            return obj.category.name
        return None


class ExpenseCreateSerializer(serializers.Serializer):
    amount = serializers.FloatField()
    description = serializers.CharField(max_length=500)
    category_id = serializers.IntegerField(required=False, allow_null=True)
    ai_label = serializers.CharField(max_length=255, required=False, allow_null=True)
