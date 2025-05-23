// Fetch GitHub activity data for the user
async function getGithubActivityData(username) {
    try {
      const response = await fetch(`https://api.github.com/users/${username}/events`, {
        headers: {
          Accept: "application/vnd.github+json",
        },
      });
      if (!response.ok) {
        throw new Error(`Error fetching GitHub activity data: ${response.status}`);
      }
    //   console.log(username);
      return await response.json();
    } catch (error) {
      console.error(error);
      return [];
    }
}
  
  // Parse GitHub event data into a readable message
function parseEventData(event, username) {
    const eventDate = event.created_at.slice(0, 10); // Get only the date part
    const eventType = event.type;
    const repoName = event.repo ? event.repo.name : "a repository";
    const repoUrl = event.repo.url
    const action = event.payload.action || "performed an action";
    let message = {
        id : event.id,
        type:'post',
        title: eventType,
        description: `${username} ${action} ${eventType} on ${repoName} on ${eventDate}`,
        content:'',
        contentType: 'text/plain',
        visibility: 'PUBLIC',
    }
    // if event type starts with PullRequest 
    if (eventType.startsWith("PullRequest")) {
        let pullrequestURL = event.payload.pull_request.html_url;
        let pullrequestbody = event.payload.pull_request.body;
        if (action == 'closed') {
            pullrequestbody = event.payload.pull_request.merged ? 'Merged' : 'Closed';
        }
        message.content = `Pull request URL: ${pullrequestURL} \n ${pullrequestbody}`;
        return message;
    }
    else if (eventType.startsWith("Issue")) {
        let issueURL = event.payload.issue.html_url;
        message.content = `Issue URL: ${issueURL}`;
        return message;
    }
    else if (eventType.startsWith("Push")) {
        let commitURL = event.payload.commits[0].url;
        let commitMessage = event.payload.commits[0].message;
        message.content = `Commit URL: ${commitURL} \n ${commitMessage}`;
        return message;
    }
    else if (eventType.startsWith("Create")) {
        let branchName = event.payload.ref;
        let des = event.payload.description;
        message.content = `Branch: ${branchName} \n Description: ${des}`;
        return message;
    }
    else if (eventType.startsWith("Delete")) {
        let branchName = event.payload.ref;
        message.content = `Branch: ${branchName}`;
        return message;
    }
    else if (eventType.startsWith("Fork")) {
        let forkURL = event.payload.forkee.html_url;
        message.content = `Fork URL: ${forkURL}`;
        return message;
    }
    else if (eventType.startsWith("Watch")) {
        message.content = `Starred the repository`;
        return message;
    }
    else if (eventType.startsWith("Release")) {
        let releaseURL = event.payload.release.html_url;
        let releaseName = event.payload.release.name;
        message.content = `Release URL: ${releaseURL} \n Release Name: ${releaseName}`;
        return message;
    }
    else if (eventType.startsWith("Public")) {
        message.content = `Made the repository public`;
        return message;
    }
    else if (eventType.startsWith("Member")) {
        let memberName = event.payload.member.login;
        message.content = `Added ${memberName} as a collaborator`;
        return message;
    }
    else if (eventType.startsWith("Gollum")) {
        let wikiURL = event.payload.pages[0].html_url;
        let wikiTitle = event.payload.pages[0].title;
        message.content = `Wiki URL: ${wikiURL} \n Wiki Title: ${wikiTitle}`;
        return message;
    }
    else if (eventType.startsWith("Issues")) {
        let issueURL = event.payload.issue.html_url;
        let issueTitle = event.payload.issue.title;
        message.content = `Issue URL: ${issueURL} \n Issue Title: ${issueTitle}`;
        return message;
    }
    else if (eventType.startsWith("Project")) {
        let projectURL = event.payload.project.html_url;
        let projectName = event.payload.project.name;
        message.content = `Project URL: ${projectURL} \n Project Name: ${projectName}`;
        return message;
    }
    else if (eventType.startsWith("Project")) {
        let projectURL = event.payload.project.html_url;
        let projectName = event.payload.project.name;
        message.content = `Project URL: ${projectURL} \n Project Name: ${projectName}`;
        return message;
    }
    else if (eventType.startsWith("Project")) {
        let projectURL = event.payload.project.html_url;
        let projectName = event.payload.project.name;
        message.content = `Project URL: ${projectURL} \n Project Name: ${projectName}`;
        return message;
    }
    else if (eventType.startsWith("Project")) {
        let projectURL = event.payload.project.html_url;
        let projectName = event.payload.project.name;
        message.content = `Project URL: ${projectURL} \n Project Name: ${projectName}`;
        return message;
    }
    else if (eventType.startsWith("Project")) {
        let projectURL = event.payload.project.html_url;
        let projectName = event.payload.project.name;
        message.content = `Project URL: ${projectURL} \n Project Name: ${projectName}`;
        return message;
    }
    else {
        message.content = `Event URL: ${repoUrl}`;
        return message;
    }


}
  
  // Function to create posts if they don't already exist
  async function createGithubActivityPosts(authorId, username) {
    try {
        // 1. Fetch GitHub activity data
        const rawData = await getGithubActivityData(username);

        // 2. Fetch existing posts
        const existingPosts = await getAllPosts(authorId);

        // 3. Process each event and render new posts
        for (const event of rawData) {
            const eventId = String(event.id);
            
            // Check if post already exists
            if (!existingPosts.some(post => post.description === eventId)) {
                // Parse and create the post
                const postContent = parseEventData(event, username);
                const res = await createPost(authorId, postContent);

                if (res === "stop") {
                    return "stop";
                }
            }
        }
    } catch (error) {
        console.error(`Error creating GitHub activity posts: ${error}`);
    }
}

  
  // Mock function to get all posts (Replace with real API call)
  async function getAllPosts(authorId) {
    // This should return a list of existing post descriptions to check duplicates
    return []; // Replace with actual data from backend
  }

  async function createPost(authorId, postObject) {
    try {
        let fullUrl = window.location.href + 'api/authors/' + authorId + '/gitPost/';
      const response = await fetch(fullUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
            "X-CSRFToken": csrftoken,
        },
        body: JSON.stringify(postObject),
      });
      if (response.status === 208) {
        // console.log(`Post already exists: ${response.status}`);
        return "stop";
      }
      return await response.json();
    } catch (error) {
      console.log()
      return null;
    }
  }


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
  
  // Render a post on the frontend
//   function renderPost(authorId, title, content, description) {
//     const postContainer = document.getElementById("post-container");
//     const postElement = document.createElement("div");
//     postElement.className = "post";
//     postElement.innerHTML = `
//       <h3>${title}</h3>
//       <p>${content}</p>
//       <small>ID: ${description}</small>
//     `;
//     postContainer.appendChild(postElement);
//   }

// make a fetch request on /api/author to get author dataa
async function getAuthorData() {
    try {
        const response = await fetch(`/api/author`);
        if (!response.ok) {
        throw new Error(`Error fetching author data: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

// Usage: Get author data and create GitHub activity posts
async function main(){
    // get author data and json parse it
    const author = await getAuthorData();

    if (author) {
        if(author.github != 'None' && author.github != '' && author.github != null) {
            createGithubActivityPosts(author.id, author.github.split("/").pop());
        }
        
    }
}

main();
