
'use strict';

window.addEventListener('load', main);

function getToken(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie != '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        // Does this cookie string begin with the name we want?
        if (cookie.substring(0,name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
   }
const csrftoken = getToken('csrftoken');

function sendRequest(followRequestsData,methodd, index) {
    // Send a PUT request to the server
    // percent encode the author1__FQID , author1__FQID is object or author who sent the request, we approve or decline the request
    let author1 = encodeURIComponent(followRequestsData[index].author1__id)
    
    const currentUrl = followRequestsData[index].author2__id + '/followers/' + author1 
    console.log("url:", currentUrl);
    fetch(`${currentUrl}`, {
        method: methodd,
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken':csrftoken
        },
        body: {}
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        // remove the element from the DOM
        document.getElementById(`followRequest-${index}`).remove();
        return response.json();
    })
    .then(data => {
        console.log('Success:', data);
    })
    .catch((error) => {
        console.error('Error:', error);
    });
}

function main() {
    // Parse the JSON data from the script tags
    let index = document.getElementById('followRequestsData').textContent.indexOf('[');
    const followRequestsData = JSON.parse(document.getElementById('followRequestsData').textContent.substring(index));
    index = document.getElementById('commentsData').textContent.indexOf('[')
    const commentsData = JSON.parse(document.getElementById('commentsData').textContent.substring(index));
    index = document.getElementById('likesData').textContent.indexOf('[')
    const likesData = JSON.parse(document.getElementById('likesData').textContent.substring(index));
    index = document.getElementById('repostData').textContent.indexOf('[')
    const repostData = JSON.parse(document.getElementById('repostData').textContent.substring(index));

    // console.log(followRequestsData); // Now you can use this data
    // console.log(commentsData); 
    // console.log(likesData); 
    // console.log(repostData);

    // Example: storing data for later use
    window.inboxData = {
        followRequests: followRequestsData,
        comments: commentsData,
        likes: likesData,
        repost: repostData
    };

    const buttonsAccept = document.querySelectorAll('.accept');
    const buttonsDecline = document.querySelectorAll('.decline');

    buttonsAccept.forEach(button => {
        button.addEventListener('click', function() {
            sendRequest(followRequestsData,'PUT', parseInt(button.closest('.action-buttons').getAttribute('data-index')));
            
        });
    });

    buttonsDecline.forEach(button => {
        button.addEventListener('click', function() {
            sendRequest(followRequestsData,'DELETE', parseInt(button.closest('.action-buttons').getAttribute('data-index')));
        });
    });
    
}