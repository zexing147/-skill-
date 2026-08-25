from __future__ import annotations
import csv, zipfile
from pathlib import Path
from xml.sax.saxutils import escape

SHEETS = {
    'accounts.csv': ('账号信息', {'sec_user_id':'账号ID','input_ref':'主页链接','nickname':'昵称','signature':'简介','follower_count':'粉丝数','following_count':'关注数','total_favorited':'获赞总数','aweme_count':'作品数'}),
    'videos.csv': ('作品信息', {'platform_video_id':'作品ID','account_id':'账号记录ID','description':'作品文案','published_at':'发布时间','video_url':'视频链接','duration_ms':'时长（毫秒）'}),
    'video-metrics.csv': ('作品指标', {'video_id':'作品记录ID','play_count':'播放数','like_count':'点赞数','comment_count':'评论数','collect_count':'收藏数','share_count':'分享数','captured_at':'采集时间'}),
    'comments.csv': ('评论', {'platform_comment_id':'评论ID','video_id':'作品记录ID','author_name':'评论者昵称','content':'评论内容','like_count':'点赞数','reply_count':'回复数','published_at':'发布时间'}),
    'api-usage.csv': ('调用记录', {'job_id':'任务ID','operation':'操作','request_status':'请求状态','http_status':'HTTP状态','error':'错误','occurred_at':'发生时间'}),
}
def col(n):
    s=''
    while n: n,r=divmod(n-1,26); s=chr(65+r)+s
    return s
def make_xlsx(folder):
    folder=Path(folder); sheets=[]
    for fn,(name,mp) in SHEETS.items():
        p=folder/fn
        if not p.exists(): continue
        with p.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.reader(f))
        if not rows: continue
        rows[0]=[mp.get(x,x) for x in rows[0]]; sheets.append((name,rows))
    out=folder/'抖音账号研究.xlsx'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        names=''.join(f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>' for i,(n,_) in enumerate(sheets,1))
        z.writestr('xl/workbook.xml',f'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{names}</sheets></workbook>')
        rels=''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))
        z.writestr('xl/_rels/workbook.xml.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        for i,(_,rows) in enumerate(sheets,1):
            body=''.join('<row>'+''.join(f'<c r="{col(c)}{r}" t="inlineStr"><is><t>{escape(v or "")}</t></is></c>' for c,v in enumerate(row,1))+'</row>' for r,row in enumerate(rows,1))
            z.writestr(f'xl/worksheets/sheet{i}.xml',f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{body}</sheetData></worksheet>')
    return out
