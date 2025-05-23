from django.shortcuts import render
from django.contrib.auth import get_user_model
from author.models import Author
import requests
import base64
from author.serializers import AuthorSerializer


User = get_user_model()

def search_results(request):
    query = request.GET.get('q', '')
    results = []
    # before we search, we need to fetch authors from other nodes and save them in our database, if they don't exist already
    # get all the node authors
    nodes = Author.objects.filter(isNode=True)
    # get host of all the nodes 
    nodehosts = [node.host for node in nodes]
    print(nodehosts)
    for node in nodes:
        # make get request to the node's url with basic auth
        headers = {
                "Authorization": f"Basic {base64.b64encode(f'{node.displayName}:{node.first_name}'.encode()).decode()}",
                "Content-Type": "application/json",
                "X-original-host":  "https://social-distribution-crimson-464113e0f29c.herokuapp.com/api/"
            }
        print(node.host + '/api/authors?size=200', node.displayName, node.first_name)
        response = requests.get( url = node.host + '/api/authors?size=200', headers=headers)
        print(response.status_code)
        if response.status_code == 200:
            authors = response.json()['authors']

            for author in authors:
                # check if the author already exists in the database
                
                if not Author.objects.filter(id=author['id'], displayName = author['displayName']).exists():
                    # save the author in the database
                    if author['host'].endswith('/api/'):
                        author['host'] = author['host'][:-5]
                    
                    if author['host'] not in nodehosts:
                        print(author['host'])
                        continue
                    author['password'] = 'password'  # set a dummy password
   
                    serializer = AuthorSerializer(data=author)
                    if serializer.is_valid():
                        serializer.save()
                    else:
                        # do not do anything for now, skip
                        print(serializer.errors)
        else:
            print(response.status_code)

    if query:
        results = User.objects.filter(displayName__icontains=query)

    return render(request, 'search.html', {'results': results, 'query': query})
