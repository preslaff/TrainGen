export default function NewPartner() {
  return (
    <form>
      <input name="business_name" data-testid="partner-business-name" aria-label="Business name" />
      <select name="category" aria-label="Category"></select>
      <select name="region" data-testid="partner-region" aria-label="Region"></select>
      <button data-testid="partner-save-draft">Save draft</button>
      <button data-testid="partner-publish">Publish</button>
    </form>
  );
}
