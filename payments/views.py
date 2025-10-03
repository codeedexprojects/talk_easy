from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import RechargePlanCatogary, RechargePlan
from .serializers import RechargePlanCategorySerializer, RechargePlanSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication


#  Category Create & List
class RechargePlanCategoryListCreateAPIView(generics.ListCreateAPIView):
    queryset = RechargePlanCatogary.objects.filter(is_deleted=False)
    serializer_class = RechargePlanCategorySerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]



#  Category Detail
class RechargePlanCategoryDetailAPIView(generics.RetrieveUpdateAPIView):
    queryset = RechargePlanCatogary.objects.filter(is_deleted=False)
    serializer_class = RechargePlanCategorySerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]


#  Category Soft Delete
class RechargePlanCategoryDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def delete(self, request, pk):
        try:
            category = RechargePlanCatogary.objects.get(pk=pk, is_deleted=False)
            category.is_deleted = True
            category.save()
            return Response({"message": "Category deleted successfully"}, status=status.HTTP_200_OK)
        except RechargePlanCatogary.DoesNotExist:
            return Response({"error": "Category not found"}, status=status.HTTP_404_NOT_FOUND)


#  Plan Create & List
class RechargePlanListCreateAPIView(generics.ListCreateAPIView):
    queryset = RechargePlan.objects.filter(is_deleted=False)
    serializer_class = RechargePlanSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]


#  Plan Detail
class RechargePlanDetailAPIView(generics.RetrieveUpdateAPIView):
    queryset = RechargePlan.objects.filter(is_deleted=False)
    serializer_class = RechargePlanSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]


#  Plan Soft Delete
class RechargePlanDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def delete(self, request, pk):
        try:
            plan = RechargePlan.objects.get(pk=pk, is_deleted=False)
            plan.is_deleted = True
            plan.save()
            return Response({"message": "Plan deleted successfully"}, status=status.HTTP_200_OK)
        except RechargePlan.DoesNotExist:
            return Response({"error": "Plan not found"}, status=status.HTTP_404_NOT_FOUND)

from rest_framework import status, permissions
from payments.models import UserRecharge

class RechargePlansView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        plans = RechargePlan.objects.filter(is_active=True, is_deleted=False)
        serializer = RechargePlanSerializer(plans, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserRechargeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        plan_id = request.data.get("plan_id")

        try:
            plan = RechargePlan.objects.get(id=plan_id, is_active=True, is_deleted=False)
        except RechargePlan.DoesNotExist:
            return Response({"error": "Invalid recharge plan"}, status=status.HTTP_400_BAD_REQUEST)

        coins_to_add = plan.get_adjusted_coin_package()
        amount_to_pay = plan.calculate_final_price()

        recharge = UserRecharge.objects.create(
            user=user,
            plan=plan,
            coins_added=coins_to_add,
            amount_paid=amount_to_pay,
            is_successful=True  
        )

        return Response({
            "message": "Recharge successful",
            "coins_added": coins_to_add,
            "amount_paid": float(amount_to_pay),
            "current_coin_balance": user.stats.coin_balance
        }, status=status.HTTP_200_OK)