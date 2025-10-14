from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import *
from .serializers import *
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from executives.authentication import ExecutiveTokenAuthentication
from django.utils.timezone import now
from rest_framework.permissions import IsAdminUser
import razorpay
from django.conf import settings


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


razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)

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

        # Razorpay expects amount in paise (integer)
        razorpay_amount = int(amount_to_pay * 100)

        # Create Razorpay order
        try:
            razorpay_order = razorpay_client.order.create({
                "amount": razorpay_amount,
                "currency": "INR",
                "payment_capture": 1,  
                "notes": {
                    "user_id": str(user.id),
                    "plan_name": plan.plan_name,
                    "coins_to_add": coins_to_add
                }
            })
        except Exception as e:
            return Response({"error": f"Failed to create Razorpay order: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        recharge = UserRecharge.objects.create(
            user=user,
            plan=plan,
            coins_added=coins_to_add,
            amount_paid=amount_to_pay,
            is_successful=False  
        )

        return Response({
            "message": "Razorpay order created successfully",
            "order_id": razorpay_order["id"],
            "amount": float(amount_to_pay),
            "currency": "INR",
            "razorpay_key": settings.RAZORPAY_KEY_ID,
            "coins_to_add": coins_to_add,
        }, status=status.HTTP_200_OK)
    

import hmac
import hashlib

class VerifyRechargePaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        razorpay_order_id = request.data.get("razorpay_order_id")
        razorpay_payment_id = request.data.get("razorpay_payment_id")
        razorpay_signature = request.data.get("razorpay_signature")

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return Response({"error": "Missing payment details"}, status=status.HTTP_400_BAD_REQUEST)

        # Verify the signature
        try:
            generated_signature = hmac.new(
                settings.RAZORPAY_KEY_SECRET.encode(),
                f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
                hashlib.sha256
            ).hexdigest()

            if generated_signature != razorpay_signature:
                return Response({"error": "Invalid signature verification"}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({"error": f"Signature verification failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Mark recharge as successful
        try:
            recharge = UserRecharge.objects.filter(user=user, is_successful=False).latest('created_at')
            recharge.is_successful = True
            recharge.save()

            return Response({
                "message": "Payment verified and recharge successful",
                "coins_added": recharge.coins_added,
                "amount_paid": float(recharge.amount_paid),
                "current_coin_balance": user.stats.coin_balance
            }, status=status.HTTP_200_OK)

        except UserRecharge.DoesNotExist:
            return Response({"error": "Pending recharge not found"}, status=status.HTTP_404_NOT_FOUND)

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
                "executiveId": redeem_request.executive.id
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


class AdminRedeemListUpdateAPIView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    # List all redemption requests
    def get(self, request):
        redeems = ExecutivePayoutRedeem.objects.all().order_by("-requested_at")
        serializer = AdminRedeemManageSerializer(redeems, many=True)
        return Response(serializer.data)

    # Update redemption request (approve/reject/paid)
    def patch(self, request, pk):
        try:
            redeem_request = ExecutivePayoutRedeem.objects.get(pk=pk)
        except ExecutivePayoutRedeem.DoesNotExist:
            return Response({"detail": "Redeem request not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminRedeemManageSerializer(redeem_request, data=request.data, partial=True)
        if serializer.is_valid():
            redeem = serializer.save()

            if redeem.status in ["approved", "rejected", "paid"]:
                redeem.processed_at = now()
                redeem.save()

            return Response(AdminRedeemManageSerializer(redeem).data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class UserRechargeHistoryViewAdmin(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes=[JWTAuthentication]  

    def get(self, request, user_id):
        try:
            user = UserProfile.objects.get(id=user_id)
        except UserProfile.DoesNotExist:
            return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        recharges = UserRecharge.objects.filter(user=user).order_by('-created_at')
        serializer = UserRechargeSerializer(recharges, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class UserRechargeHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        recharges = UserRecharge.objects.filter(user=user).order_by('-created_at')
        serializer = UserRechargeSerializer(recharges, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
    
class AdminRechargeView(APIView):

    permission_classes = [permissions.IsAdminUser]
    authentication_classes=[JWTAuthentication]

    def post(self, request):
        user_id = request.data.get("user_id")
        plan_id = request.data.get("plan_id")
        coins_to_add = request.data.get("coins_added")
        amount_paid = request.data.get("amount_paid")

        if not user_id:
            return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = UserProfile.objects.get(id=user_id)
        except UserProfile.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        # # Optional: allow using a plan, or custom input
        # plan = None
        # if plan_id:
        #     try:
        #         plan = RechargePlan.objects.get(id=plan_id, is_active=True, is_deleted=False)
        #         coins_to_add = coins_to_add or plan.get_adjusted_coin_package()
        #         amount_paid = amount_paid or plan.calculate_final_price()
        #     except RechargePlan.DoesNotExist:
        #         return Response({"error": "Invalid recharge plan"}, status=status.HTTP_400_BAD_REQUEST)
        # else:
        #     if not all([coins_to_add, amount_paid]):
        #         return Response(
        #             {"error": "Either plan_id or both coins_added and amount_paid are required"},
        #             status=status.HTTP_400_BAD_REQUEST,
        #         )

        recharge = UserRecharge.objects.create(
            user=user,
            plan=RechargePlan,
            coins_added=coins_to_add,
            amount_paid=amount_paid,
            is_successful=True,
            by_admin=True,
            payment_status="successful",
        )

        if hasattr(user, "stats"):
            user.stats.coin_balance += int(coins_to_add)
            user.stats.save(update_fields=["coin_balance"])

        return Response({
            "message": f"Recharge successful for user {user}",
            "coins_added": int(coins_to_add),
            "amount_paid": float(amount_paid),
            "current_coin_balance": user.stats.coin_balance,
        }, status=status.HTTP_200_OK)