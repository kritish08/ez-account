import React, { useState, useEffect, useCallback } from "react";
import { Check, ChevronsUpDown, Package, Loader2 } from "lucide-react";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "./ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "./ui/popover";
import { getProducts, getProduct } from "../lib/api";

// Local debounce — avoids pulling in lodash (~70KB) just for one helper.
const debounce = (fn, wait) => {
  let timer;
  const debounced = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
  debounced.cancel = () => clearTimeout(timer);
  return debounced;
};

export function SearchableProductSelect({ 
  products: initialProducts = [], 
  value, 
  onValueChange, 
  placeholder = "Search product...", 
  includeManual = false,
  itemType = null // "RAW_MATERIAL" or "FINISHED_GOOD"
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [options, setOptions] = useState(initialProducts);
  const [selectedProduct, setSelectedProduct] = useState(null);

  // Fetch the specifically selected product if it's not in the options
  useEffect(() => {
    if (value && value !== "manual_entry") {
      const found = options.find(p => p.id === value);
      if (found) {
        setSelectedProduct(found);
      } else {
        getProduct(value)
          .then(res => setSelectedProduct(res.data))
          .catch(err => console.error("Error fetching selected product:", err));
      }
    } else {
      setSelectedProduct(null);
    }
  }, [value, options]);

  // Debounced search function
  const fetchProducts = useCallback(
    debounce(async (query) => {
      setLoading(true);
      try {
        const params = { search: query };
        if (itemType) params.item_type = itemType;
        const res = await getProducts(params);
        setOptions(res.data);
      } catch (err) {
        console.error("Error searching products:", err);
      } finally {
        setLoading(false);
      }
    }, 300),
    [itemType]
  );

  // Initial fetch when popover opens
  useEffect(() => {
    if (open && options.length === 0) {
      fetchProducts("");
    }
  }, [open, options.length, fetchProducts]);

  const isManual = value === "manual_entry";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal bg-white"
        >
          {isManual ? (
            "Free text item"
          ) : selectedProduct ? (
            <div className="flex items-center gap-2 truncate">
              <Package className="h-4 w-4 text-slate-400 shrink-0" />
              <span className="truncate">{selectedProduct.name}</span>
            </div>
          ) : (
            <span className="text-muted-foreground">{placeholder}</span>
          )}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[320px] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput 
            placeholder="Search product name or SKU..." 
            value={search}
            onValueChange={(val) => {
              setSearch(val);
              fetchProducts(val);
            }}
          />
          <CommandList>
            {loading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
              </div>
            ) : (
              <>
                <CommandEmpty>No product found.</CommandEmpty>
                <CommandGroup>
                  {includeManual && (
                    <CommandItem
                      value={"manual_entry"}
                      onSelect={() => {
                        onValueChange("manual_entry");
                        setOpen(false);
                      }}
                    >
                      <Check
                        className={cn(
                          "mr-2 h-4 w-4",
                          value === "manual_entry" ? "opacity-100" : "opacity-0"
                        )}
                      />
                      Free text item
                    </CommandItem>
                  )}
                  {options.map((p) => (
                    <CommandItem
                      key={p.id}
                      value={p.id}
                      onSelect={() => {
                        onValueChange(p.id);
                        setOpen(false);
                      }}
                    >
                      <Check
                        className={cn(
                          "mr-2 h-4 w-4 shrink-0",
                          value === p.id ? "opacity-100" : "opacity-0"
                        )}
                      />
                      <div className="flex items-center gap-2 w-full pr-2">
                        <Package className="h-4 w-4 text-slate-400 shrink-0" />
                        <span className="truncate flex-1">{p.name}</span>
                        <span className="text-xs text-slate-400 shrink-0 tabular-nums">
                          {p.current_stock} in stock
                        </span>
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
