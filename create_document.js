const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell } = require('docx');
const fs = require('fs');

// Create the document
const doc = new Document({
  sections: [{
    properties: {},
    children: [
      // Title
      new Paragraph({
        heading: 'Title',
        children: [
          new TextRun({
            text: '欢迎使用 Mini-Agent',
            bold: true,
            size: 36,
          }),
        ],
      }),

      // Paragraphs with formatting
      new Paragraph({
        children: [
          new TextRun({ text: '这是一个加粗文本', bold: true }),
          new TextRun({ text: '，这是一个倾斜文本', italics: true }),
          new TextRun({ text: '，这是一个带下划线的文本', underline: {} }),
        ],
      }),

      new Paragraph({
        children: [
          new TextRun({ text: '你可以在这里添加更多内容！', color: 'FF0000' }),
        ],
      }),

      // Simple table
      new Table({
        columnWidths: [4500, 4500],
        rows: [
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ children: [new TextRun('第一列')] })],
              }),
              new TableCell({
                children: [new Paragraph({ children: [new TextRun('第二列')] })],
              }),
            ],
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ children: [new TextRun('示例内容 1')] })],
              }),
              new TableCell({
                children: [new Paragraph({ children: [new TextRun('示例内容 2')] })],
              }),
            ],
          }),
        ],
      }),
    ],
  }],
});

// Save the document
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync('example.docx', buffer);
  console.log('文档已创建：example.docx');
});