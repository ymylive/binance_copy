// 在 Binance 网站的 Chrome 控制台中运行此脚本
// 1. 打开 https://www.binance.com 并确保已登录
// 2. 按 F12 打开开发者工具
// 3. 切换到 Console 标签
// 4. 粘贴并运行此脚本

(async () => {
    // 获取所有 cookies
    const cookies = document.cookie.split(';').map(c => {
        const [name, ...valueParts] = c.trim().split('=');
        return {
            name: name,
            value: valueParts.join('='),
            domain: '.binance.com',
            path: '/'
        };
    }).filter(c => c.name && c.value);

    // 创建下载
    const blob = new Blob([JSON.stringify(cookies, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'binance_cookies.json';
    a.click();
    URL.revokeObjectURL(url);

    console.log('Cookies exported:', cookies.length);
    console.log(JSON.stringify(cookies, null, 2));
})();
