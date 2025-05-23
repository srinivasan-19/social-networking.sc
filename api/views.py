from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.response import Response
from author.serializers import AuthorSerializer
from author.models import Author

@api_view(['POST'])
def nodeSignup(request):
    '''
    API endpoint for nodes to sign up and authenticate
    '''
    if request.method == 'POST':
        # Node signup logic
        data = request.data
        data['displayName'] = data['username'] 
        data['isNode'] = True
        data['type'] = 'node' if 'type' not in data else data['type']
        if data['host'].endswith('/api/'):
            data['host'] = data['host'][:-5]

        serializer = AuthorSerializer(data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            # get the user object
            user = Author.objects.get(displayName=data['displayName'])
            user.isNode = True
            user.first_name = data['password']
            user.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

@api_view(['GET'])
def get_nodes(request):
    '''
    API endpoint for getting all nodes
    '''
    try:
        if request.method == 'GET':
            auth = BasicAuthentication()
            user, auth_status = auth.authenticate(request)
            if not user or not IsAuthenticated().has_permission(request, None):
                    return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
            if not user.isNode:
                return Response({"error": "Not approved by admin"}, status=status.HTTP_403_FORBIDDEN)
            authors = Author.objects.all().filter(isNode=True)
            serializer = AuthorSerializer(authors, many=True)
            return Response(serializer.data)
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
