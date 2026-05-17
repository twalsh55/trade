import Image from "next/image";
import Link from "next/link";

type BrandMarkProps = {
  href?: string | null;
  size?: "sm" | "md" | "lg";
  priority?: boolean;
  className?: string;
  imageClassName?: string;
};

export function BrandMark({
  href = "/",
  size = "md",
  priority = false,
  className = "",
  imageClassName = "",
}: BrandMarkProps) {
  const sizeClass =
    size === "lg"
      ? "h-14 w-14 rounded-[1.2rem]"
      : size === "sm"
        ? "h-9 w-9 rounded-[0.9rem]"
        : "h-11 w-11 rounded-[1rem]";

  const image = (
    <Image
      src="/logo.png"
      alt="Brivoly logo"
      width={96}
      height={96}
      priority={priority}
      className={`${sizeClass} object-contain ${imageClassName}`.trim()}
    />
  );

  if (!href) {
    return <div className={className}>{image}</div>;
  }

  return (
    <Link href={href} className={className}>
      {image}
    </Link>
  );
}
