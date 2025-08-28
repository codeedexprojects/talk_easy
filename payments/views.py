from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import RechargePlanCatogary, RechargePlan
from .serializers import RechargePlanCategorySerializer, RechargePlanSerializer

#  Category Create & List
class RechargePlanCategoryListCreateAPIView(generics.ListCreateAPIView):
    queryset = RechargePlanCatogary.objects.filter(is_deleted=False)
    serializer_class = RechargePlanCategorySerializer


#  Category Detail
class RechargePlanCategoryDetailAPIView(generics.RetrieveAPIView):
    queryset = RechargePlanCatogary.objects.filter(is_deleted=False)
    serializer_class = RechargePlanCategorySerializer


#  Category Soft Delete
class RechargePlanCategoryDeleteAPIView(APIView):
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


#  Plan Detail
class RechargePlanDetailAPIView(generics.RetrieveAPIView):
    queryset = RechargePlan.objects.filter(is_deleted=False)
    serializer_class = RechargePlanSerializer


#  Plan Soft Delete
class RechargePlanDeleteAPIView(APIView):
    def delete(self, request, pk):
        try:
            plan = RechargePlan.objects.get(pk=pk, is_deleted=False)
            plan.is_deleted = True
            plan.save()
            return Response({"message": "Plan deleted successfully"}, status=status.HTTP_200_OK)
        except RechargePlan.DoesNotExist:
            return Response({"error": "Plan not found"}, status=status.HTTP_404_NOT_FOUND)
