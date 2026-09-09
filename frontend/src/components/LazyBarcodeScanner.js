import React, { Suspense, lazy } from "react";

// html5-qrcode is the single heaviest dependency in the tree, and every page
// that imported BarcodeScanner directly pulled it into the main bundle — so
// it shipped to every user on every page, including people who never scan
// anything.
//
// Deferring the import isn't enough on its own: each call site renders
// <BarcodeScanner open={...}> unconditionally and lets the component decide
// whether to show itself, which would fetch the chunk on mount anyway. This
// wrapper renders nothing until the scanner is actually opened, so the chunk
// is fetched the first time someone taps Scan.
const BarcodeScanner = lazy(() => import("./BarcodeScanner"));

const LazyBarcodeScanner = (props) => {
  if (!props.open) return null;
  return (
    <Suspense fallback={null}>
      <BarcodeScanner {...props} />
    </Suspense>
  );
};

export default LazyBarcodeScanner;
