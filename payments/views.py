from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import *
from .serializers import *
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from executives.authentication import ExecutiveTokenAuthentication


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
    

class RedemptionOptionListCreateAPIView(APIView):
    permission_classes=[]

    def get(self, request):
        options = RedemptionOption.objects.filter(is_deleted=False)
        serializer = RedemptionOptionSerializer(options, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = RedemptionOptionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RedemptionOptionDetailAPIView(APIView):

    def get_object(self, pk):
        try:
            return RedemptionOption.objects.get(pk=pk, is_deleted=False)
        except RedemptionOption.DoesNotExist:
            return None

    def get(self, request, pk):
        option = self.get_object(pk)
        if not option:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = RedemptionOptionSerializer(option)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        option = self.get_object(pk)
        if not option:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = RedemptionOptionSerializer(option, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        option = self.get_object(pk)
        if not option:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = RedemptionOptionSerializer(option, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        option = self.get_object(pk)
        if not option:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        option.is_deleted = True
        option.save()
        return Response({"detail": "Deleted successfully"}, status=status.HTTP_204_NO_CONTENT)
    
class RedemptionOptionListViewExecutive(APIView):
    permission_classes=[IsAuthenticated]
    authentication_classes=[ExecutiveTokenAuthentication]

    def get(self, request):
        options = RedemptionOption.objects.filter(is_deleted=False)
        serializer = RedemptionOptionSerializer(options, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class ExecutiveRedeemAPIView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [ExecutiveTokenAuthentication]  

    def post(self, request):
        executive = getattr(request, "user", None)  

        if not executive:
            return Response({"detail": "Executive not found or not authenticated."},
                            status=status.HTTP_401_UNAUTHORIZED)

        stats = getattr(executive, "stats", None)
        if not stats:
            return Response({"detail": "Executive stats not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ExecutiveRedeemSerializer(data=request.data)
        if serializer.is_valid():
            redemption_option = serializer.validated_data["redemption_option"]
            redeem_amount = redemption_option.amount

            if stats.pending_payout < redeem_amount:
                return Response({"detail": "Insufficient pending payout to redeem this amount."},
                                status=status.HTTP_400_BAD_REQUEST)

            stats.pending_payout -= Decimal(redeem_amount)
            stats.save()

            redeem_request = ExecutivePayoutRedeem.objects.create(
                executive=executive,
                redemption_option=redemption_option,
                status="pending",
                upi_details=serializer.validated_data.get("upi_details"),
                account_number=serializer.validated_data.get("account_number"),
                ifsc_code=serializer.validated_data.get("ifsc_code")
            )

            return Response({
                "detail": "Redemption request created successfully.",
                "request_id": redeem_request.id,
                "amount": redeem_amount,
                "status": redeem_request.status,
                "executiveId":redeem_request.executive
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class ExecutiveRedeemHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [ExecutiveTokenAuthentication]

    def get(self, request):
        executive = getattr(request, "user", None)

        if not executive:
            return Response({"detail": "Executive not found or not authenticated."},
                            status=401)

        redeems = ExecutivePayoutRedeem.objects.filter(executive=executive).order_by("-requested_at")
        serializer = ExecutiveRedeemHistorySerializer(redeems, many=True)

        return Response(serializer.data)