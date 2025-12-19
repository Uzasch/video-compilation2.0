const http = require('http');

const OLD_HOST = '192.168.1.83';
const NEW_HOST = '192.168.1.173';
const PORT = 3000;

http.createServer((req, res) => {
    const newUrl = `http://${NEW_HOST}:${PORT}${req.url}`;
    console.log(`Redirecting: ${req.url} -> ${newUrl}`);
    res.writeHead(302, { 'Location': newUrl });
    res.end();
}).listen(PORT, OLD_HOST, () => {
    console.log(`Redirect server running on http://${OLD_HOST}:${PORT}`);
    console.log(`Redirecting all traffic to http://${NEW_HOST}:${PORT}`);
});
