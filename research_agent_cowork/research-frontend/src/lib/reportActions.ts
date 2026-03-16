function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

export async function copyTextToClipboard(value: string) {
  await navigator.clipboard.writeText(value);
}

export function downloadMarkdownBlob(blob: Blob, filename: string) {
  downloadBlob(blob, filename);
}

export async function exportElementToPdf(element: HTMLElement, filename: string) {
  const container = document.createElement('div');
  container.style.position = 'absolute';
  container.style.left = '-9999px';
  container.style.top = '0';
  container.style.width = '900px';
  document.body.appendChild(container);

  try {
    const { default: html2pdf } = await import('html2pdf.js');
    const clonedElement = element.cloneNode(true) as HTMLElement;
    clonedElement.classList.add('pdf-export-mode');
    clonedElement.style.padding = '28px';
    clonedElement.style.maxWidth = '860px';
    clonedElement.style.width = '860px';
    clonedElement.style.margin = '0 auto';
    container.appendChild(clonedElement);

    type PdfOptions = {
      margin: [number, number, number, number];
      filename: string;
      image: {
        type: 'jpeg';
        quality: number;
      };
      html2canvas: {
        scale: number;
        useCORS: boolean;
        letterRendering: boolean;
        backgroundColor: string;
      };
      jsPDF: {
        unit: string;
        format: string;
        orientation: 'portrait';
      };
      pagebreak: {
        mode: string[];
        avoid: string[];
      };
    };

    const pdfOptions: PdfOptions = {
      margin: [12, 8, 12, 8],
      filename,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: {
        scale: 2,
        useCORS: true,
        letterRendering: true,
        backgroundColor: '#ffffff',
      },
      jsPDF: {
        unit: 'mm',
        format: 'a4',
        orientation: 'portrait',
      },
      pagebreak: {
        mode: ['css', 'legacy'],
        avoid: ['pre', 'blockquote', 'table', 'img', '.rb-card', '.rb-section', '.rb-hero'],
      },
    };

    const pdfWorker = html2pdf() as {
      set: (options: PdfOptions) => {
        from: (element: HTMLElement) => {
          save: () => Promise<void>;
        };
      };
    };

    await pdfWorker.set(pdfOptions).from(clonedElement).save();
  } finally {
    document.body.removeChild(container);
  }
}
