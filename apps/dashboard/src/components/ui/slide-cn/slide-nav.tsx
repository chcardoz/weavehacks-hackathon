"use client";
import { Button } from "@/components/ui/button";
import { useDeck } from "@/components/ui/slide-cn/deck";
import { ChevronLeft, ChevronRight } from "lucide-react";

/**
 * SlideNav
 *
 * SlideNav is already included in the deck component by default. You dont need to touch this component unless you want to modify how changing slides works
 */

export function SlideNav() {
	const deck = useDeck();

	return (
		<>
			{/* LEFT ZONE */}
			<div className="hidden md:block pointer-events-none absolute inset-y-0 left-0 w-24">
				<div className="group pointer-events-auto h-full w-full flex items-center">
					<Button
						type="button"
						onClick={deck.prev}
						variant="outline"
						size="icon"
							className="
								ml-4
								border-white
								bg-black
								text-white
								opacity-0
								transition-opacity
								group-hover:opacity-100
								hover:bg-black
								hover:text-white"
					>
						<ChevronLeft className="size-4" />
						<span className="sr-only">Previous slide</span>
					</Button>
				</div>
			</div>

			{/* RIGHT ZONE */}
			<div className="hidden md:block pointer-events-none absolute inset-y-0 right-0 w-24">
				<div className="group pointer-events-auto h-full w-full flex items-center justify-end">
					<Button
						type="button"
						onClick={deck.next}
						variant="outline"
						size="icon"
							className="
	              mr-4
	              border-white
	              bg-black
	              text-white
	              opacity-0
	              transition-opacity
	              group-hover:opacity-100
	              hover:bg-black
	              hover:text-white
	            "
					>
						<ChevronRight className="size-4" />
						<span className="sr-only">Next slide</span>
					</Button>
				</div>
			</div>
		</>
	);
}
