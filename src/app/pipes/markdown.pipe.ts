import { Pipe, PipeTransform } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Converts markdown-style SOW text to HTML for beautiful display.
 * Handles: # ## ### headers, **bold**, * lists, ---, and tables.
 */
@Pipe({ name: 'markdown', standalone: true })
export class MarkdownPipe implements PipeTransform {
  constructor(private sanitizer: DomSanitizer) {}

  transform(value: string): SafeHtml {
    if (!value?.trim()) return this.sanitizer.bypassSecurityTrustHtml('');
    const lines = value.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
    const out: string[] = [];
    let i = 0;
    let inTable = false;
    let tableRows: string[] = [];
    let inList = false;

    function flushList(): void {
      if (inList) {
        out.push('</ul>');
        inList = false;
      }
    }

    function flushTable(): void {
      if (!inTable || tableRows.length === 0) return;
      flushList();
      const [headerRow, ...bodyRows] = tableRows;
      const headerCells = headerRow.split('|').filter((c) => c.trim().length > 0).map((c) => c.trim());
      const isSeparator = (row: string) => /^[\s|:\-]+$/.test(row);
      const dataRows = bodyRows.filter((row) => !isSeparator(row));
      let tableHtml = '<table class="sow-table"><thead><tr>';
      headerCells.forEach((cell) => {
        tableHtml += `<th>${processInline(cell)}</th>`;
      });
      tableHtml += '</tr></thead><tbody>';
      dataRows.forEach((row) => {
        const cells = row.split('|').filter((c) => c.trim().length > 0).map((c) => c.trim());
        tableHtml += '<tr>';
        cells.forEach((cell) => {
          tableHtml += `<td>${processInline(cell)}</td>`;
        });
        tableHtml += '</tr>';
      });
      tableHtml += '</tbody></table>';
      out.push(tableHtml);
      tableRows = [];
      inTable = false;
    }

    function processInline(text: string): string {
      return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    }

    function isTableRow(l: string): boolean {
      return l.includes('|') && (l.trim().startsWith('|') || /\|.+\|/.test(l));
    }

    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();

      if (isTableRow(trimmed)) {
        flushList();
        if (!inTable) flushTable();
        inTable = true;
        tableRows.push(trimmed);
        i++;
        continue;
      }

      flushTable();

      if (trimmed.startsWith('### ')) {
        flushList();
        out.push(`<h3 class="sow-h3">${processInline(trimmed.slice(4))}</h3>`);
      } else if (trimmed.startsWith('## ')) {
        flushList();
        out.push(`<h2 class="sow-h2">${processInline(trimmed.slice(3))}</h2>`);
      } else if (trimmed.startsWith('# ')) {
        flushList();
        out.push(`<h1 class="sow-h1">${processInline(trimmed.slice(2))}</h1>`);
      } else if (trimmed === '---') {
        flushList();
        out.push('<hr class="sow-hr" />');
      } else if (trimmed.startsWith('*   ') || trimmed.startsWith('* ')) {
        const content = trimmed.startsWith('*   ') ? trimmed.slice(4) : trimmed.slice(2);
        if (!inList) {
          out.push('<ul class="sow-ul">');
          inList = true;
        }
        out.push(`<li class="sow-li">${processInline(content)}</li>`);
      } else if (/^\d+\.\s+/.test(trimmed)) {
        const match = /^\d+\.\s+(.*)$/.exec(trimmed);
        if (match) {
          if (!inList) {
            out.push('<ul class="sow-ul sow-ul-num">');
            inList = true;
          }
          out.push(`<li class="sow-li sow-li-num">${processInline(match[1])}</li>`);
        }
      } else if (trimmed === '') {
        flushList();
        out.push('<br />');
      } else {
        flushList();
        out.push(`<p class="sow-p">${processInline(trimmed)}</p>`);
      }
      i++;
    }

    flushList();
    flushTable();

    const html = out.join('');
    const wrapped = `<div class="sow-markdown">${html}</div>`;
    return this.sanitizer.bypassSecurityTrustHtml(wrapped);
  }
}
