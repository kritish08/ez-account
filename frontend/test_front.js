const http = require('http');

http.get('http://localhost:3000', (res) => {
  let data = '';
  res.on('data', chunk => data += chunk);
  res.on('end', () => {
    if (data.includes('<div id="root"></div>')) {
      console.log('Frontend served HTML fine.');
    } else {
      console.log('Frontend HTML missing root div.');
    }
  });
}).on('error', err => console.log('Error fetching frontend:', err.message));
