'use strict';
// Shared presentation vocabulary. Only structured visitor evidence is read.
const VisitorView = {
  rows(out, spanish) {
    const pick = (en, es) => spanish ? es : en;
    const fields = {password:pick('Password','Contraseña'), verification_code:pick('Code','Código'), payment:pick('Payment','Pago'), sign_in:pick('Sign-in','Inicio de sesión'), file_upload:pick('File upload','Subir archivo')};
    const profiles = [['android_mobile','📱',pick('Phone','Teléfono')], ['desktop_chrome','💻',pick('Computer','Computadora')], ['alternate','🌐',pick('Another browser','Otro navegador')]];
    const rows = profiles.map(([profile, icon, label]) => {
      const v = (out.visitors || []).find(v => v.profile === profile || (profile === 'alternate' && v.profile === 'desktop_firefox'));
      return {icon, label, host:v?.final_host || '', reached:v?.reached_page === true,
        fields:Object.keys(fields).filter(key => v?.requested?.includes(key)).map(key => fields[key]),
        signature:JSON.stringify([v?.final_host || '',v?.reached_page === true,Object.keys(fields).filter(key => v?.requested?.includes(key))])};
    });
    const counts = rows.map(r => rows.filter(other => other.signature === r.signature).length);
    const largest = Math.max(...counts);
    return rows.map((r,i) => ({...r, differs:counts[i] < largest || largest === 1,
      status:r.reached ? pick('✓ Page reached','✓ Se llegó a la página') : pick("✕ Couldn't reach the site",'✕ No se pudo acceder al sitio')}));
  },
  spoken(out, spanish) {
    return this.rows(out, spanish).map(r => [r.label,r.host,r.status,...r.fields].filter(Boolean).join('. ')).join('. ');
  }
};
