from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# 创建一个 PDF 文件
c = canvas.Canvas("example.pdf", pagesize=letter)
width, height = letter

# 添加标题
c.setFont("Helvetica-Bold", 18)
c.drawString(100, height - 100, "示例 PDF 文件")

# 添加正文
c.setFont("Helvetica", 12)
c.drawString(100, height - 150, "这是一个使用 Python 和 reportlab 生成的 PDF 文件。")

# 保存 PDF
c.save()