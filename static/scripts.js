function loadContent(page) {
    const content = document.getElementById('content');

    fetch(`/components/${page}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok ' + response.statusText);
            }
            return response.text();
        })
        .then(data => {
            content.innerHTML = data;

            // Update active link styling
            const links = document.querySelectorAll('.sidebar-menu ul li a');
            links.forEach(link => link.classList.remove('active'));

            const activeLink = Array.from(links).find(link => link.href.includes(page));
            if (activeLink) activeLink.classList.add('active');
        })
        .catch(error => {
            content.innerHTML = `<p>Error loading content: ${error.message}</p>`;
        });
}
