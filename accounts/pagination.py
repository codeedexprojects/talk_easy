from rest_framework.pagination import PageNumberPagination

class CustomUserPagination(PageNumberPagination):
    page_size = 50 
    page_size_query_param = 'page_size'
    max_page_size = 1000
    
    def get_page_size(self, request):
        if 'limit' in request.query_params:
            try:
                limit = int(request.query_params['limit'])
                if limit > 0:
                    return min(limit, self.max_page_size)
            except ValueError:
                pass
        return super().get_page_size(request)

class CustomExecutivePagination(PageNumberPagination):
    page_size = 50  
    page_size_query_param = 'page_size'
    max_page_size = 1000

    def get_page_size(self, request):
        if 'limit' in request.query_params:
            try:
                limit = int(request.query_params['limit'])
                if limit > 0:
                    return min(limit, self.max_page_size)
            except ValueError:
                pass
        return super().get_page_size(request)