export class CRMCallLog {
  async onRender() {
    if (this.doc.name) return
    const defaults = await this.call(
      'crm.fcrm.doctype.crm_call_log.crm_call_log.get_manual_call_defaults',
      {
        reference_doctype: this.doc.reference_doctype || '',
        reference_docname: this.doc.reference_docname || '',
      },
    )
    const incoming = this.doc.type === 'Incoming'
    if (incoming) {
      ;[defaults.from, defaults.to] = [defaults.to, defaults.from]
      defaults.receiver = defaults.caller
      defaults.caller = null
    }
    for (const [field, value] of Object.entries(defaults)) {
      if (!this.doc[field]) this.doc[field] = value
    }
  }

  type() {
    if (this.doc.name || !this.oldValue || this.oldValue === this.doc.type)
      return
    ;[this.doc.from, this.doc.to] = [this.doc.to, this.doc.from]
    ;[this.doc.caller, this.doc.receiver] = [
      this.doc.receiver || null,
      this.doc.caller || null,
    ]
  }
}
