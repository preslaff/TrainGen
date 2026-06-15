import Link from "next/link";

export default function PartnersList() {
  return (
    <div>
      <button data-testid="partners-add-btn" aria-label="Add partner">Add partner</button>
      <Link href="/admin/partners/1" aria-label="Open partner">Open</Link>
    </div>
  );
}
