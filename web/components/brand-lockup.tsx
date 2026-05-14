import Image from "next/image";
import Link from "next/link";

type BrandLockupProps = {
  href?: string;
  size?: "md" | "lg" | "xl";
  priority?: boolean;
};

export function BrandLockup({
  href = "/",
  size = "lg",
  priority = false,
}: BrandLockupProps) {
  const sizeClass =
    size === "xl"
      ? "h-24 w-24 rounded-[1.75rem]"
      : size === "lg"
        ? "h-20 w-20 rounded-[1.5rem]"
        : "h-16 w-16 rounded-[1.25rem]";

  return (
    <Link href={href} className="inline-flex rounded-[1.75rem]">
      <Image
        src="/logo.png"
        alt="Trade logo"
        width={96}
        height={96}
        priority={priority}
        className={`${sizeClass} object-contain`}
      />
    </Link>
  );
}
