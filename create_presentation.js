const PptxGenJS = require('pptxgenjs');
const pptx = new PptxGenJS();

// 1. 添加标题幻灯片
pptx.addSlide({
  masterName: 'TITLE_SLIDE',
  title: '欢迎使用 Mini-Agent',
  subtitle: '一个强大的 AI 助手',
});

// 2. 添加文本幻灯片
pptx.addSlide({
  masterName: 'MASTER_SLIDE',
  title: '功能介绍',
  text: [
    { text: '• 创建和编辑文档（Word、PPT 等）', options: { bullet: true } },
    { text: '• 提供智能建议和分析', options: { bullet: true } },
    { text: '• 支持多种文件格式', options: { bullet: true } },
  ],
});

// 3. 添加图片幻灯片
pptx.addSlide({
  title: '示例图片',
  background: { color: 'F2F2F2' },
  images: [
    { 
      path: 'D:\mini code\Mini-Agent\example.png', // 替换为实际图片路径
      x: 1, y: 1.5, w: 6, h: 4.5,
      sizing: { type: 'cover' },
    },
  ],
});

// 保存 PPT 文件
pptx.writeFile({ fileName: 'example.pptx' })
  .then(() => console.log('PPT 演示文稿已创建：example.pptx'))
  .catch(err => console.error('创建失败:', err));