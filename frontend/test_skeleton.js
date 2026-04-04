const puppeteer = require('puppeteer');

(async () => {
  try {
    const browser = await puppeteer.launch({ args: ['--no-sandbox'] });
    const page = await browser.newPage();
    
    console.log("Navigating to dashboard...");
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle0' });
    
    // Evaluate in browser context
    const styles = await page.evaluate(() => {
      const el = document.querySelector('.animate-pulse');
      if (!el) return 'No skeleton element found with .animate-pulse';
      
      const computed = window.getComputedStyle(el);
      return {
        className: el.className,
        backgroundColor: computed.backgroundColor,
        boxShadow: computed.boxShadow,
        filter: computed.filter,
        opacity: computed.opacity,
        border: computed.border
      };
    });
    
    console.log("Computed Styles:", styles);
    
    await browser.close();
  } catch (e) {
    console.error("Error:", e);
    process.exit(1);
  }
})();
